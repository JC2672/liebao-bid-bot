import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FolderOpen, RotateCcw, Check, Sparkles, Trash2, Upload } from "lucide-react";
import {
  bulkGenerate,
  bulkRemove,
  bulkRetry,
  generateOpportunity,
  importShortlist,
  listProfiles,
  listQueue,
  markApplied,
  openFolder,
  removeOpportunity,
  retryOpportunity,
  type OpportunityStatus,
} from "../lib/api";
import { ProfileDropdown } from "../components/ProfileDropdown";
import { SearchBox } from "../components/SearchBox";
import { Button, Card, Checkbox, IconButton, StatusBadge, TBody, THead, Table, Td, Th, Tr } from "../components/ui";
import { matchesSearch } from "../lib/search";

export function QueuePage({
  active,
  focusProfile,
}: {
  active: boolean;
  // Set by App.tsx right after Fetch's "Auto-queue & generate" hands a job
  // straight to Queue with no manual step in between - Queue needs to land
  // on that same profile, or the newly-queued/generating rows are sitting
  // there correct but invisible behind whatever profile this page's own
  // dropdown happened to be on. Not used for anything else - normal
  // browsing keeps this page's profile selection independent of Fetch's.
  focusProfile?: string;
}) {
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState<string>("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [search, setSearch] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (focusProfile) setProfile(focusProfile);
  }, [focusProfile]);

  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  const activeProfile = profile || profilesQuery.data?.[0]?.id || "";

  const queueQuery = useQuery({
    queryKey: ["queue", activeProfile],
    queryFn: () => listQueue(activeProfile),
    enabled: !!activeProfile,
    // only poll while this tab is actually visible - no point burning
    // requests refreshing a table nobody's looking at
    refetchInterval: active ? 5000 : false,
  });
  const rows = queueQuery.data ?? [];
  const filteredRows = useMemo(
    () => rows.filter((r) => matchesSearch(search, [r.company, r.title])),
    [rows, search],
  );

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["queue", activeProfile] });

  // Tracked separately from importMutation.data on purpose: React Query
  // keeps a mutation's `data` around indefinitely until that same mutation
  // fires again, so reading it directly meant this note kept showing a
  // stale "+X added, Y already queued" long after other actions (bulk
  // remove, applied, profile switch) had made it meaningless - confirmed
  // live as the "status label doesn't sync" report. `clearAndInvalidate`
  // below explicitly drops it wherever the queue changes some other way.
  const [importNotice, setImportNotice] = useState<{ inserted: number; skipped: number } | null>(null);
  const clearAndInvalidate = () => {
    setImportNotice(null);
    invalidate();
  };

  const importMutation = useMutation({
    mutationFn: (file: File) => importShortlist(activeProfile, file),
    onSuccess: (data) => {
      setImportNotice(data);
      invalidate();
    },
  });
  const appliedMutation = useMutation({ mutationFn: markApplied, onSuccess: clearAndInvalidate });
  const removeMutation = useMutation({ mutationFn: removeOpportunity, onSuccess: clearAndInvalidate });
  const retryMutation = useMutation({ mutationFn: retryOpportunity, onSuccess: clearAndInvalidate });
  const generateMutation = useMutation({ mutationFn: generateOpportunity, onSuccess: clearAndInvalidate });
  const bulkRemoveMutation = useMutation({
    mutationFn: bulkRemove,
    onSuccess: () => {
      setSelected(new Set());
      clearAndInvalidate();
    },
  });
  const bulkRetryMutation = useMutation({
    mutationFn: bulkRetry,
    onSuccess: () => {
      setSelected(new Set());
      clearAndInvalidate();
    },
  });
  const bulkGenerateMutation = useMutation({
    mutationFn: bulkGenerate,
    onSuccess: () => {
      setSelected(new Set());
      clearAndInvalidate();
    },
  });

  const allSelected =
    filteredRows.length > 0 && filteredRows.every((r) => selected.has(r.id));
  const someSelected = selected.size > 0 && !allSelected;

  // A running batch is treated as an exclusive process, confirmed live as
  // a real need: retrying two rows still waiting their turn mid-batch
  // didn't actually stop them (fixed server-side - see generation.py's
  // early-exit check in run_generation()). Kept deliberately simple per
  // the user's own call: while anything for this profile is actively
  // `generating`, EVERY other non-ready row is locked - queued, failed,
  // generating, doesn't matter - no exceptions, no escape hatch. Generate/
  // Retry/Remove all refuse it, with a tooltip explaining why rather than
  // just going quietly disabled. Failed rows are never auto-retried by
  // any of this - they just sit there locked like everything else until
  // the run ends, same as before.
  const locked = rows.some((r) => r.status === "generating");
  const rowLocked = (status: OpportunityStatus) => locked && status !== "ready";

  const selectedRetryableCount = useMemo(
    () =>
      rows.filter(
        (r) => selected.has(r.id) && !rowLocked(r.status) && (r.status === "failed" || r.status === "generating"),
      ).length,
    [rows, selected, locked],
  );
  const selectedQueuedCount = useMemo(
    () => rows.filter((r) => selected.has(r.id) && !rowLocked(r.status) && r.status === "queued").length,
    [rows, selected, locked],
  );
  const selectedRemovableIds = useMemo(
    () => rows.filter((r) => selected.has(r.id) && !rowLocked(r.status)).map((r) => r.id),
    [rows, selected, locked],
  );

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(filteredRows.map((r) => r.id)));
  }
  function toggleOne(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const selectionLabel = allSelected
    ? `All selected (${filteredRows.length})`
    : `${selected.size} selected`;

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-wrap items-center gap-4 p-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-fg-muted">Profile</label>
          <ProfileDropdown
            profiles={profilesQuery.data ?? []}
            value={activeProfile}
            onChange={(id) => {
              setProfile(id);
              setSelected(new Set());
              setImportNotice(null);
            }}
          />
        </div>

        {/* An invisible label spacer, matching the Profile block's real one
            above, so this button's top edge lines up with the dropdown's
            rather than sitting centered a bit higher against the row. */}
        <div className="flex flex-col gap-1.5">
          <label className="invisible text-xs">Import</label>
          <input
            ref={fileInput}
            type="file"
            accept=".xlsx"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) importMutation.mutate(file);
              e.target.value = "";
            }}
          />
          <Button
            variant="primary"
            disabled={!activeProfile || importMutation.isPending}
            onClick={() => fileInput.current?.click()}
          >
            <Upload size={14} />
            {importMutation.isPending ? "Importing…" : "Import"}
          </Button>
        </div>

        {importNotice && (
          <span className="text-sm text-fg-muted">
            +{importNotice.inserted} added, {importNotice.skipped} already applied/queued
          </span>
        )}
      </Card>

      <Card className="p-4">
        {/* Selection toolbar - always present above the table, not just
            when something is selected, so it has a stable position. */}
        <div className="mb-3 flex flex-wrap items-center gap-3 border-b border-border pb-3">
          <Checkbox
            checked={allSelected}
            disabled={filteredRows.length === 0}
            ref={(el) => {
              if (el) el.indeterminate = someSelected;
            }}
            onChange={toggleAll}
          />
          <span className="text-sm text-fg-muted">{selectionLabel}</span>
          <SearchBox value={search} onChange={setSearch} className="ml-2" />
          {/* Unchecking the header checkbox (above) clears the selection -
              no separate "Clear selection" button needed. */}
          <div className="ml-auto flex items-center gap-1">
            <IconButton
              title={
                locked
                  ? "A batch is already generating - wait for it to finish before starting another"
                  : `Generate ${selectedQueuedCount} selected`
              }
              tone="primary"
              badge={selectedQueuedCount}
              disabled={selectedQueuedCount === 0 || bulkGenerateMutation.isPending}
              onClick={() => bulkGenerateMutation.mutate([...selected])}
            >
              <Sparkles size={16} />
            </IconButton>
            <IconButton
              title={
                locked
                  ? "A batch is generating - wait for it to finish before retrying anything"
                  : `Retry ${selectedRetryableCount} selected`
              }
              badge={selectedRetryableCount}
              disabled={selectedRetryableCount === 0 || bulkRetryMutation.isPending}
              onClick={() => bulkRetryMutation.mutate([...selected])}
            >
              <RotateCcw size={16} />
            </IconButton>
            <IconButton
              title={
                locked && selectedRemovableIds.length < selected.size
                  ? "A batch is generating - only ready rows can be removed until it finishes"
                  : `Remove ${selectedRemovableIds.length} selected`
              }
              tone="danger"
              disabled={selectedRemovableIds.length === 0 || bulkRemoveMutation.isPending}
              onClick={() => bulkRemoveMutation.mutate(selectedRemovableIds)}
            >
              <Trash2 size={16} />
            </IconButton>
          </div>
        </div>

        <Table>
          <THead>
            <Tr>
              <Th className="w-8" />
              <Th>Company</Th>
              <Th>Title</Th>
              <Th>Location</Th>
              <Th>Status</Th>
              <Th>Actions</Th>
            </Tr>
          </THead>
          <TBody>
            {filteredRows.map((o, i) => {
              const waitTitle = "A batch is generating - wait for it to finish first";
              const rowIsLocked = rowLocked(o.status);
              const generateDisabled = o.status !== "queued" || generateMutation.isPending || rowIsLocked;
              const retryDisabled =
                retryMutation.isPending || rowIsLocked || (o.status !== "failed" && o.status !== "generating");
              const removeDisabled = removeMutation.isPending || rowIsLocked;
              // Dimmed while a batch runs, unless this row IS the one
              // actively generating (the live/current one, not locked out
              // of anything - there's nothing to lock, it's already the
              // process) or already `ready` (finished before this run even
              // started, untouched by it either way).
              const dimmed = locked && o.status !== "generating" && o.status !== "ready";
              return (
                <Tr
                  key={o.id}
                  className={`animate-fade-in-up ${dimmed ? "opacity-50" : ""} ${
                    selected.has(o.id) ? "bg-accent-wash" : ""
                  }`}
                  style={{
                    animationDelay: `${Math.min(i, 20) * 15}ms`,
                    ...(dimmed ? { "--fade-in-target-opacity": 0.5 } : {}),
                  } as CSSProperties}
                >
                  <Td>
                    <Checkbox checked={selected.has(o.id)} onChange={() => toggleOne(o.id)} />
                  </Td>
                  <Td className="font-medium">{o.company}</Td>
                  <Td>{o.title}</Td>
                  <Td className="text-fg-muted">{o.location}</Td>
                  <Td>
                    <StatusBadge status={o.status} />
                    {/* `error` doubles as a live in-progress note while
                        generating (e.g. "waiting for you to sign in") - not
                        an actual failure yet, so it's shown in a neutral
                        tone rather than the red used once status is really
                        `failed`. */}
                    {o.error && (
                      <span className={`ml-2 text-xs ${o.status === "failed" ? "text-bad" : "text-fg-muted"}`}>
                        {o.error}
                      </span>
                    )}
                  </Td>
                  <Td>
                    <div className="flex items-center gap-1">
                      <IconButton title="Open job post" onClick={() => window.open(o.url, "_blank")}>
                        <ExternalLink size={16} />
                      </IconButton>
                      <IconButton
                        title="Open folder"
                        disabled={!o.staging_dir}
                        onClick={() => openFolder(o.id)}
                      >
                        <FolderOpen size={16} />
                      </IconButton>
                      <IconButton
                        title={rowIsLocked ? waitTitle : "Generate"}
                        tone="primary"
                        disabled={generateDisabled}
                        onClick={() => generateMutation.mutate(o.id)}
                      >
                        <Sparkles size={16} />
                      </IconButton>
                      <IconButton
                        title={rowIsLocked ? waitTitle : "Retry"}
                        disabled={retryDisabled}
                        onClick={() => retryMutation.mutate(o.id)}
                      >
                        <RotateCcw size={16} />
                      </IconButton>
                      <IconButton
                        title="Mark applied"
                        tone="primary"
                        disabled={o.status !== "ready" || appliedMutation.isPending}
                        onClick={() => appliedMutation.mutate(o.id)}
                      >
                        <Check size={16} />
                      </IconButton>
                      <IconButton
                        title={rowIsLocked ? waitTitle : "Remove"}
                        tone="danger"
                        disabled={removeDisabled}
                        onClick={() => removeMutation.mutate(o.id)}
                      >
                        <Trash2 size={16} />
                      </IconButton>
                    </div>
                  </Td>
                </Tr>
              );
            })}
            {filteredRows.length === 0 && (
              <Tr>
                <Td colSpan={6} className="py-8 text-center text-fg-muted">
                  {rows.length === 0
                    ? "Queue is empty for this profile. Import a shortlist to get started."
                    : `No results match "${search}".`}
                </Td>
              </Tr>
            )}
          </TBody>
        </Table>
      </Card>
    </div>
  );
}
