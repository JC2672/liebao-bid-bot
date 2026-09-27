import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import {
  exportShortlist,
  runFetch,
  SOURCE_OPTIONS,
  type FetchCounts,
  type GateResult,
} from "../lib/api";
import { Badge, Button, Card, FlagBadge, TBody, THead, Table, Td, Th, Tr } from "../components/ui";

export function FetchPage() {
  const [sources, setSources] = useState<string[]>(["linkedin", "indeed"]);
  const [query, setQuery] = useState("Salesforce");
  const [postedWithinDays, setPostedWithinDays] = useState(7);
  const [results, setResults] = useState<GateResult[]>([]);
  const [counts, setCounts] = useState<FetchCounts | null>(null);
  const [showRejected, setShowRejected] = useState(false);
  const [includeRejectedInExport, setIncludeRejectedInExport] = useState(false);

  const fetchMutation = useMutation({
    mutationFn: () => runFetch(sources, query, postedWithinDays),
    onSuccess: (data) => {
      setResults(data.results);
      setCounts(data.counts);
    },
  });

  const exportMutation = useMutation({
    mutationFn: () =>
      exportShortlist(includeRejectedInExport ? results : results.filter((r) => r.passed)),
  });

  const visible = useMemo(
    () => results.filter((r) => showRejected || r.passed),
    [results, showRejected],
  );

  function toggleSource(id: string) {
    setSources((prev) => (prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]));
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
                  onClick={() => toggleSource(s.id)}
                  className={`rounded-md border px-2.5 py-1 text-sm transition-colors ${
                    sources.includes(s.id)
                      ? "border-accent bg-accent-wash text-accent"
                      : "border-border text-fg-muted hover:text-fg"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-fg-muted">Query</label>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-52 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs text-fg-muted">Posted within (days)</label>
            <input
              type="number"
              min={1}
              value={postedWithinDays}
              onChange={(e) => setPostedWithinDays(Number(e.target.value))}
              className="w-24 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
            />
          </div>

          <Button
            variant="primary"
            disabled={sources.length === 0 || fetchMutation.isPending}
            onClick={() => fetchMutation.mutate()}
          >
            {fetchMutation.isPending ? "Fetching…" : "Run Fetch"}
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

        {fetchMutation.isError && (
          <p className="mt-3 text-sm text-bad">Fetch failed. Is the backend running on :8000?</p>
        )}
      </Card>

      {results.length > 0 && (
        <Card className="p-4">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-4">
              <label className="flex items-center gap-2 text-sm text-fg-muted">
                <input
                  type="checkbox"
                  checked={showRejected}
                  onChange={(e) => setShowRejected(e.target.checked)}
                />
                Show rejected
              </label>
              <label className="flex items-center gap-2 text-sm text-fg-muted">
                <input
                  type="checkbox"
                  checked={includeRejectedInExport}
                  onChange={(e) => setIncludeRejectedInExport(e.target.checked)}
                />
                Include rejected in export
              </label>
            </div>
            <Button
              variant="primary"
              disabled={
                exportMutation.isPending ||
                (includeRejectedInExport ? results.length === 0 : results.every((r) => !r.passed))
              }
              onClick={() => exportMutation.mutate()}
            >
              Export Shortlist (.xlsx)
            </Button>
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
  );
}
