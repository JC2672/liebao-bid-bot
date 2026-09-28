import { useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, FolderOpen, RotateCcw, Check, Trash2 } from "lucide-react";
import {
  bulkRemove,
  bulkRetry,
  importShortlist,
  listProfiles,
  listQueue,
  markApplied,
  openFolder,
  removeOpportunity,
  retryOpportunity,
} from "../lib/api";
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

  const importMutation = useMutation({
    mutationFn: (file: File) => importShortlist(activeProfile, file),
    onSuccess: invalidate,
  });
  const appliedMutation = useMutation({ mutationFn: markApplied, onSuccess: invalidate });
  const removeMutation = useMutation({ mutationFn: removeOpportunity, onSuccess: invalidate });
  const retryMutation = useMutation({ mutationFn: retryOpportunity, onSuccess: invalidate });
  const bulkRemoveMutation = useMutation({
    mutationFn: bulkRemove,
    onSuccess: () => {
      setSelected(new Set());
      invalidate();
    },
  });
  const bulkRetryMutation = useMutation({
    mutationFn: bulkRetry,
    onSuccess: () => {
      setSelected(new Set());
      invalidate();
    },
  });

  const allSelected = rows.length > 0 && selected.size === rows.length;
  const someSelected = selected.size > 0 && !allSelected;
  const selectedFailedCount = useMemo(
    () => rows.filter((r) => selected.has(r.id) && r.status === "failed").length,
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
          <select
            value={activeProfile}
            onChange={(e) => {
              setProfile(e.target.value);
              setSelected(new Set());
            }}
            className="w-56 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
          >
            {profilesQuery.data?.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>

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
          {importMutation.isPending ? "Importing…" : "Import Shortlist (.xlsx)"}
        </Button>

        {importMutation.data && (
          <span className="text-sm text-fg-muted">
            +{importMutation.data.inserted} added, {importMutation.data.skipped} already
            applied/queued
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
              title={`Retry ${selectedFailedCount} selected`}
              badge={selectedFailedCount}
              disabled={selectedFailedCount === 0 || bulkRetryMutation.isPending}
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
                  {o.status === "failed" && o.error && (
                    <span className="ml-2 text-xs text-bad">{o.error}</span>
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
                      title="Retry"
                      disabled={o.status !== "failed"}
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
