import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, Download } from "lucide-react";
import {
  checkJobrightStatus,
  exportShortlist,
  getFetchStatus,
  listProfiles,
  startFetch,
  sourceIconUrl,
  SOURCE_OPTIONS,
  triggerJobrightLogin,
  type FetchCounts,
  type GateResult,
} from "../lib/api";
import { LoadingOverlay, type LoadingOverlayRow } from "../components/LoadingOverlay";
import { ProfileDropdown } from "../components/ProfileDropdown";
import { Badge, Button, Card, FlagBadge, TBody, THead, Table, Td, Th, Tr } from "../components/ui";

// A split "Export" button: the label itself exports the shortlist (the
// common case), the chevron opens a menu for the less-common "everything,
// including rejected" export - replaces a separate "include rejected"
// checkbox that most fetches never touched.
function ExportMenu({
  passedCount,
  totalCount,
  pending,
  onExport,
}: {
  passedCount: number;
  totalCount: number;
  pending: boolean;
  onExport: (scope: "shortlist" | "all") => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <div className="flex">
        <Button
          variant="primary"
          className="rounded-r-none"
          disabled={pending || passedCount === 0}
          onClick={() => onExport("shortlist")}
        >
          <Download size={14} />
          Export
        </Button>
        <button
          type="button"
          disabled={pending || totalCount === 0}
          onClick={() => setOpen((o) => !o)}
          aria-label="Export options"
          className="inline-flex items-center rounded-r-md border-y border-r border-accent-hover bg-accent px-1.5 text-accent-fg transition-colors hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ChevronDown size={14} />
        </button>
      </div>

      {open && (
        <div className="absolute right-0 z-10 mt-1 w-56 overflow-hidden rounded-md border border-border bg-surface shadow-lg">
          <button
            disabled={passedCount === 0}
            onClick={() => {
              onExport("shortlist");
              setOpen(false);
            }}
            className="block w-full px-3 py-2 text-left text-sm hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            Shortlist Only
            <span className="ml-1.5 text-xs text-fg-muted">({passedCount} passed)</span>
          </button>
          <button
            disabled={totalCount === 0}
            onClick={() => {
              onExport("all");
              setOpen(false);
            }}
            className="block w-full border-t border-border px-3 py-2 text-left text-sm hover:bg-surface-hover disabled:cursor-not-allowed disabled:opacity-40"
          >
            Full List
            <span className="ml-1.5 text-xs text-fg-muted">({totalCount} total, incl. rejected)</span>
          </button>
        </div>
      )}
    </div>
  );
}

export function FetchPage() {
  const queryClient = useQueryClient();
  const [sources, setSources] = useState<string[]>(["linkedin", "indeed"]);
  const [profile, setProfile] = useState<string>("");
  const [postedWithinDays, setPostedWithinDays] = useState(7);
  const [results, setResults] = useState<GateResult[]>([]);
  const [counts, setCounts] = useState<FetchCounts | null>(null);
  const [showRejected, setShowRejected] = useState(false);
  const [jobrightNotice, setJobrightNotice] = useState<string | null>(null);

  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  // No field/query input here anymore - the selected profile's own field
  // (query term/title list/relevance keywords, see backend/app/fields.py)
  // drives every source now, so Fetch needs to know which profile this
  // run is for up front, the same way Queue already does.
  const activeProfile = profile || profilesQuery.data?.[0]?.id || "";

  const jobrightSelected = sources.includes("jobright");
  // Live status badge - reads the dedicated Jobright browser profile's
  // session (see backend/app/jobright_browser.py), checked via a real
  // request to Jobright's own API (jobright_session.check_session()), not
  // just "was a cookie file saved". Polls while selected and not yet
  // signed in, so the badge flips on its own once the user finishes
  // signing in in the window Run Fetch opened - no need to click Run
  // Fetch again just to re-check.
  const jobrightStatusQuery = useQuery({
    queryKey: ["jobright-status"],
    queryFn: checkJobrightStatus,
    enabled: jobrightSelected,
    refetchInterval: (query) => (jobrightSelected && !query.state.data?.logged_in ? 3000 : false),
  });

  // A fetch is now a background job (see routers/fetch.py): POST /fetch/start
  // kicks it off and returns immediately, and this polls GET /fetch/status
  // for real per-source progress (surfaced in LoadingOverlay as a literal
  // checklist) plus the eventual result - there's no single request to
  // await here the way the old one-shot POST /fetch worked.
  const [isFetchActive, setIsFetchActive] = useState(false);
  const [fetchJobError, setFetchJobError] = useState<string | null>(null);

  const startFetchMutation = useMutation({
    mutationFn: () => startFetch(sources, activeProfile, postedWithinDays),
    onSuccess: () => setIsFetchActive(true),
  });

  const statusQuery = useQuery({
    queryKey: ["fetch-status"],
    queryFn: getFetchStatus,
    enabled: isFetchActive,
    refetchInterval: isFetchActive ? 400 : false,
  });

  const isFetching = startFetchMutation.isPending || isFetchActive;

  useEffect(() => {
    if (!isFetchActive) return;
    const status = statusQuery.data;
    if (status && !status.running) {
      if (status.result) {
        setResults(status.result.results);
        setCounts(status.result.counts);
      }
      if (status.error) {
        setFetchJobError(status.error);
      }
      setIsFetchActive(false);
    }
  }, [isFetchActive, statusQuery.data]);

  const exportMutation = useMutation({
    mutationFn: (rows: GateResult[]) => exportShortlist(rows),
  });

  const visible = useMemo(
    () => results.filter((r) => showRejected || r.passed),
    [results, showRejected],
  );

  // What LoadingOverlay actually renders: each currently-selected source,
  // paired with its live backend status if a poll has come back yet (else
  // "pending" - nothing's been reported for it, which is also true at that
  // moment), so there's no flash of an empty checklist right after
  // clicking Run Fetch and before the first status response lands.
  const progressRows: LoadingOverlayRow[] = useMemo(() => {
    const live = new Map(statusQuery.data?.sources.map((s) => [s.name, s]) ?? []);
    return sources.map((id) => {
      const opt = SOURCE_OPTIONS.find((s) => s.id === id);
      const liveSource = live.get(id);
      return {
        name: id,
        domain: opt?.domain ?? "",
        label: opt?.label ?? id,
        status: liveSource?.status ?? "pending",
        count: liveSource?.count ?? null,
      };
    });
  }, [sources, statusQuery.data]);

  function toggleSource(id: string) {
    setSources((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));
  }

  async function handleRunFetch() {
    setJobrightNotice(null);
    setFetchJobError(null);
    if (jobrightSelected) {
      const status = await checkJobrightStatus();
      queryClient.setQueryData(["jobright-status"], status);
      if (!status.logged_in) {
        await triggerJobrightLogin();
        setJobrightNotice(
          "Opened a Jobright sign-in window - sign in there. The badge above will update on its own once you're signed in.",
        );
        return; // don't fetch this round - wait for the user to actually sign in; nothing of the old list should be touched yet
      }
    }

    // Clear the old list right before the new fetch starts, rather than
    // leaving it sitting there dimmed under the loading overlay until the
    // new results arrive and overwrite it - a re-run should read as "that
    // list is gone, a new one is being built," not "the old one, paused."
    clearResults();
    // Also drop any cached /fetch/status from the previous run - otherwise,
    // if this run selects the same sources, the checklist can briefly flash
    // the previous run's "done" ticks before the first fresh poll lands.
    queryClient.removeQueries({ queryKey: ["fetch-status"] });
    startFetchMutation.mutate();
  }

  function clearResults() {
    setResults([]);
    setCounts(null);
  }

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-4">
        <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-fg-muted">Sources</label>
            <div className="flex flex-wrap gap-1.5">
              {SOURCE_OPTIONS.map((s) => (
                <button
                  key={s.id}
                  disabled={isFetching}
                  onClick={() => toggleSource(s.id)}
                  className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                    sources.includes(s.id)
                      ? "border-accent bg-accent-wash text-accent"
                      : "border-border text-fg-muted hover:text-fg"
                  }`}
                >
                  <img
                    src={sourceIconUrl(s.domain)}
                    alt=""
                    className="h-4 w-4 shrink-0"
                    onError={(e) => {
                      e.currentTarget.style.display = "none";
                    }}
                  />
                  {s.label}
                </button>
              ))}
            </div>
            {jobrightSelected && (
              <div className="mt-2">
                {jobrightStatusQuery.isLoading ? (
                  <Badge>Jobright: checking sign-in status…</Badge>
                ) : jobrightStatusQuery.data?.logged_in ? (
                  <Badge tone="good">Jobright: signed in</Badge>
                ) : (
                  <Badge tone="warn">Jobright: not signed in - Run Fetch will open a sign-in window</Badge>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-fg-muted">Profile</label>
            <ProfileDropdown
              profiles={profilesQuery.data ?? []}
              value={activeProfile}
              disabled={isFetching}
              onChange={setProfile}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-fg-muted">Posted within (days)</label>
            <input
              type="number"
              min={1}
              value={postedWithinDays}
              disabled={isFetching}
              onChange={(e) => setPostedWithinDays(Number(e.target.value))}
              className="w-24 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent disabled:cursor-not-allowed disabled:opacity-50"
            />
          </div>

          <Button
            variant="primary"
            disabled={sources.length === 0 || !activeProfile || isFetching}
            onClick={handleRunFetch}
          >
            {isFetching ? "Fetching…" : "Run Fetch"}
          </Button>

          {counts && (
            <div className="ml-auto flex gap-2">
              <Badge>{counts.fetched} fetched</Badge>
              <Badge>{counts.deduped} deduped</Badge>
              <Badge tone="good">{counts.passed} passed</Badge>
              <Badge tone="bad">{counts.rejected} rejected</Badge>
            </div>
          )}
        </div>

        {jobrightNotice && <p className="mt-3 text-sm text-warn">{jobrightNotice}</p>}
        {startFetchMutation.isError && (
          <p className="mt-3 text-sm text-bad">Fetch failed to start. Is the backend running on :8000?</p>
        )}
        {fetchJobError && <p className="mt-3 text-sm text-bad">Fetch failed: {fetchJobError}</p>}
      </Card>

      {/* The loading overlay's own area: scoped to just the results list,
          beneath the configuration panel above (which disables its own
          controls directly, rather than being covered by this). Needs a
          standing min-height while pending with nothing fetched yet (first
          run, or right after Clear results) - otherwise there's no "list"
          for an absolutely-positioned overlay to size itself against. */}
      <div className="relative">
        {isFetching && <LoadingOverlay sources={progressRows} />}

        {results.length === 0 && isFetching && <div className="h-64" />}

        {results.length > 0 && (
          <Card className="p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-sm text-fg-muted">
                <input
                  type="checkbox"
                  checked={showRejected}
                  onChange={(e) => setShowRejected(e.target.checked)}
                />
                Show rejected
              </label>
              <div className="flex gap-2">
                <Button variant="ghost" onClick={clearResults}>
                  Clear results
                </Button>
                <ExportMenu
                  passedCount={results.filter((r) => r.passed).length}
                  totalCount={results.length}
                  pending={exportMutation.isPending}
                  onExport={(scope) =>
                    exportMutation.mutate(scope === "shortlist" ? results.filter((r) => r.passed) : results)
                  }
                />
              </div>
            </div>

            <Table>
              <THead>
                <Tr>
                  <Th>Company</Th>
                  <Th>Title</Th>
                  <Th>Location</Th>
                  <Th>Source</Th>
                  <Th>Flags / Reason</Th>
                  <Th>Posted</Th>
                </Tr>
              </THead>
              <TBody>
                {visible.map((r) => (
                  <Tr key={`${r.source}-${r.external_id}`} className={!r.passed ? "opacity-50" : ""}>
                    <Td className="font-medium">{r.company}</Td>
                    <Td>
                      <a href={r.url} target="_blank" rel="noreferrer" className="hover:text-accent hover:underline">
                        {r.title}
                      </a>
                    </Td>
                    <Td className="text-fg-muted">{r.location}</Td>
                    <Td className="text-fg-muted" mono>
                      {r.source}
                    </Td>
                    <Td>
                      <div className="flex flex-wrap gap-1">
                        {!r.passed && <Badge tone="bad">{r.reject_reason}</Badge>}
                        {r.flags.map((f) => (
                          <FlagBadge key={f} flag={f} />
                        ))}
                      </div>
                    </Td>
                    <Td className="text-fg-muted" mono>
                      {r.posted_at ? new Date(r.posted_at).toLocaleDateString() : "—"}
                    </Td>
                  </Tr>
                ))}
              </TBody>
            </Table>
          </Card>
        )}
      </div>
    </div>
  );
}
