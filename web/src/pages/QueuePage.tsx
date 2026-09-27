import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  importShortlist,
  listProfiles,
  listQueue,
  markApplied,
  openFolder,
  removeOpportunity,
  retryOpportunity,
} from "../lib/api";
import { Button, Card, StatusBadge } from "../components/ui";

export function QueuePage() {
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState<string>("");
  const fileInput = useRef<HTMLInputElement>(null);

  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  const activeProfile = profile || profilesQuery.data?.[0]?.id || "";

  const queueQuery = useQuery({
    queryKey: ["queue", activeProfile],
    queryFn: () => listQueue(activeProfile),
    enabled: !!activeProfile,
    refetchInterval: 5000, // picks up status changes once the generation engine (Phase 3) runs
  });

  const importMutation = useMutation({
    mutationFn: (file: File) => importShortlist(activeProfile, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue", activeProfile] }),
  });

  const appliedMutation = useMutation({
    mutationFn: markApplied,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue", activeProfile] }),
  });
  const removeMutation = useMutation({
    mutationFn: removeOpportunity,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue", activeProfile] }),
  });
  const retryMutation = useMutation({
    mutationFn: retryOpportunity,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["queue", activeProfile] }),
  });

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-wrap items-center gap-4 p-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs text-fg-muted">Profile</label>
          <select
            value={activeProfile}
            onChange={(e) => setProfile(e.target.value)}
            className="w-56 rounded-md border border-border bg-surface-hover px-2.5 py-1.5 text-sm outline-none focus:border-accent"
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
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-fg-muted">
              <tr className="border-b border-border">
                <th className="py-2 pr-3">Company</th>
                <th className="py-2 pr-3">Title</th>
                <th className="py-2 pr-3">Location</th>
                <th className="py-2 pr-3">Status</th>
                <th className="py-2 pr-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {queueQuery.data?.map((o) => (
                <tr key={o.id} className="border-b border-border/50">
                  <td className="py-2 pr-3 font-medium">{o.company}</td>
                  <td className="py-2 pr-3">{o.title}</td>
                  <td className="py-2 pr-3 text-fg-muted">{o.location}</td>
                  <td className="py-2 pr-3">
                    <StatusBadge status={o.status} />
                    {o.status === "failed" && o.error && (
                      <span className="ml-2 text-xs text-bad">{o.error}</span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <div className="flex flex-wrap gap-2">
                      <Button variant="ghost" onClick={() => window.open(o.url, "_blank")}>
                        Open Post
                      </Button>
                      <Button
                        variant="ghost"
                        disabled={!o.staging_dir}
                        onClick={() => openFolder(o.id)}
                      >
                        Open Folder
                      </Button>
                      {o.status === "failed" && (
                        <Button variant="secondary" onClick={() => retryMutation.mutate(o.id)}>
                          Retry
                        </Button>
                      )}
                      <Button
                        variant="primary"
                        disabled={o.status !== "ready" || appliedMutation.isPending}
                        onClick={() => appliedMutation.mutate(o.id)}
                      >
                        Applied
                      </Button>
                      <Button variant="danger" onClick={() => removeMutation.mutate(o.id)}>
                        Remove
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {queueQuery.data?.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-fg-muted">
                    Queue is empty for this profile. Import a shortlist to get started.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
