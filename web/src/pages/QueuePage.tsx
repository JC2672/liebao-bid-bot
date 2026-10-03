import { useMemo, useRef, useState } from "react";
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
} from "../lib/api";
import { ProfileDropdown } from "../components/ProfileDropdown";
import { Button, Card, Checkbox, IconButton, StatusBadge, TBody, THead, Table, Td, Th, Tr } from "../components/ui";

export function QueuePage({ active }: { active: boolean }) {
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState<string>("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const fileInput = useRef<HTMLInputElement>(null);

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

  const allSelected = rows.length > 0 && selected.size === rows.length;
  const someSelected = selected.size > 0 && !allSelected;
  // Retry also covers `generating` - the escape hatch for a row stuck
  // there with nothing actually working on it anymore (closed the
  // ChatGPT window mid-run, backend restarted mid-run, etc.).
  const selectedRetryableCount = useMemo(
    () => rows.filter((r) => selected.has(r.id) && (r.status === "failed" || r.status === "generating")).length,
    [rows, selected],
  );
  const selectedQueuedCount = useMemo(
    () => rows.filter((r) => selected.has(r.id) && r.status === "queued").length,
    [rows, selected],
  );

  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(rows.map((r) => r.id)));
  }
  function toggleOne(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const selectionLabel = allSelected
    ? `All selected (${rows.length})`
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
            disabled={rows.length === 0}
            ref={(el) => {
              if (el) el.indeterminate = someSelected;
            }}
            onChange={toggleAll}
          />
          <span className="text-sm text-fg-muted">{selectionLabel}</span>
          {/* Unchecking the header checkbox (above) clears the selection -
              no separate "Clear selection" button needed. */}
          <div className="ml-auto flex items-center gap-1">
            <IconButton
              title={`Generate ${selectedQueuedCount} selected`}
              tone="primary"
              badge={selectedQueuedCount}
              disabled={selectedQueuedCount === 0 || bulkGenerateMutation.isPending}
              onClick={() => bulkGenerateMutation.mutate([...selected])}
            >
              <Sparkles size={16} />
            </IconButton>
            <IconButton
              title={`Retry ${selectedRetryableCount} selected`}
              badge={selectedRetryableCount}
              disabled={selectedRetryableCount === 0 || bulkRetryMutation.isPending}
              onClick={() => bulkRetryMutation.mutate([...selected])}
            >
              <RotateCcw size={16} />
            </IconButton>
            <IconButton
              title={`Remove ${selected.size} selected`}
              tone="danger"
              disabled={selected.size === 0 || bulkRemoveMutation.isPending}
              onClick={() => bulkRemoveMutation.mutate([...selected])}
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
            {rows.map((o) => (
              <Tr key={o.id} className={selected.has(o.id) ? "bg-accent-wash" : ""}>
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
                      title="Generate"
                      tone="primary"
                      disabled={o.status !== "queued" || generateMutation.isPending}
                      onClick={() => generateMutation.mutate(o.id)}
                    >
                      <Sparkles size={16} />
                    </IconButton>
                    <IconButton
                      title="Retry"
                      disabled={o.status !== "failed" && o.status !== "generating"}
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
                    <IconButton title="Remove" tone="danger" onClick={() => removeMutation.mutate(o.id)}>
                      <Trash2 size={16} />
                    </IconButton>
                  </div>
                </Td>
              </Tr>
            ))}
            {rows.length === 0 && (
              <Tr>
                <Td colSpan={6} className="py-8 text-center text-fg-muted">
                  Queue is empty for this profile. Import a shortlist to get started.
                </Td>
              </Tr>
            )}
          </TBody>
        </Table>
      </Card>
    </div>
  );
}
