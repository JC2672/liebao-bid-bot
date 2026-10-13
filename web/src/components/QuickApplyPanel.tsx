import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, FolderOpen, RefreshCw, RotateCcw, Trash2, X, Zap } from "lucide-react";
import {
  listProfiles,
  listQueue,
  markApplied,
  openFolder,
  quickApply,
  removeOpportunity,
  retryOpportunity,
} from "../lib/api";
import { Button, StatusBadge } from "./ui";
import { DatePicker } from "./DatePicker";
import { Field } from "./Field";
import { ProfileDropdown } from "./ProfileDropdown";

const EMPTY_FORM = {
  profile: "",
  company: "",
  title: "",
  source: "",
  posted_at: "",
  url: "",
  description: "",
};

/** A side panel for the one job that didn't come through Fetch at all - a
 * recruiter email, a posting found by hand - where running the whole
 * fetch/dedupe/queue pipeline for a single row is pure overhead and the
 * actual need is "generate this one resume right now." Mounted once at
 * the App level (not inside any one tab) so it's reachable everywhere
 * except Setup, per the user's own call - Setup is itself a
 * configuration screen, not a place you'd be reacting to a live job lead
 * from.
 *
 * Tracks exactly one job at a time, by design, not a list - confirmed
 * with the user directly: Quick Apply is inherently a one-at-a-time
 * action ("executed per a job post"), so there's nothing to show a list
 * of. Submitting moves the panel from the entry form to tracking that
 * one row's live status with Mark Applied/Retry/Remove right there,
 * exactly the "follow up to it" the feature was asked for - once that
 * row is applied-to or removed, the panel resets to a blank form, ready
 * for the next one. */
export function QuickApplyPanel({ hidden }: { hidden: boolean }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [trackedId, setTrackedId] = useState<number | null>(null);
  const [trackedProfile, setTrackedProfile] = useState<string>("");

  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });

  // Reuses the same /queue list + poll every other screen already uses,
  // rather than a dedicated single-row endpoint that doesn't otherwise
  // exist - the tracked row is just whichever id matches in that list.
  const trackedQueueQuery = useQuery({
    queryKey: ["queue", trackedProfile],
    queryFn: () => listQueue(trackedProfile),
    enabled: open && trackedId !== null && !!trackedProfile,
    refetchInterval: open && trackedId !== null ? 3000 : false,
  });
  const trackedRow = trackedQueueQuery.data?.find((r) => r.id === trackedId);

  const invalidateTracked = () => queryClient.invalidateQueries({ queryKey: ["queue", trackedProfile] });

  function backToForm() {
    setTrackedId(null);
    setTrackedProfile("");
    setForm(EMPTY_FORM);
  }

  const submitMutation = useMutation({
    mutationFn: () =>
      quickApply({
        profile: form.profile,
        company: form.company,
        title: form.title,
        source: form.source,
        posted_at: form.posted_at,
        url: form.url,
        description: form.description,
      }),
    onSuccess: (data) => {
      if (data.id !== null) {
        setTrackedId(data.id);
        setTrackedProfile(form.profile);
        queryClient.invalidateQueries({ queryKey: ["queue", form.profile] });
      }
    },
  });

  const appliedMutation = useMutation({
    mutationFn: markApplied,
    onSuccess: backToForm,
  });
  const removeMutation = useMutation({
    mutationFn: removeOpportunity,
    onSuccess: backToForm,
  });
  const retryMutation = useMutation({
    mutationFn: retryOpportunity,
    onSuccess: invalidateTracked,
  });

  const canSubmit =
    !!form.profile && !!form.company.trim() && !!form.title.trim() && !!form.url.trim() && !!form.description.trim();

  if (hidden) return null;

  return (
    <>
      {/* A fixed tab docked to the right edge, not a header icon - lives on
          the same edge the drawer itself slides in from, so it reads as
          that drawer's own handle rather than another header control
          competing for space. Fades out (rather than unmounting) once the
          drawer is open, in step with the drawer's own slide-in, instead of
          popping away the instant it's clicked. */}
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Quick Apply"
        title="Quick Apply - add a single job found outside Fetch"
        className={`fixed right-0 top-1/2 z-40 flex -translate-y-1/2 flex-col items-center gap-1.5 rounded-l-md border border-r-0 border-border bg-surface px-1.5 py-3 text-fg-muted shadow-md transition-[opacity,color] duration-300 hover:text-accent ${
          open ? "pointer-events-none opacity-0" : "opacity-100"
        }`}
      >
        <Zap size={16} />
        <span className="text-[11px] font-medium [writing-mode:vertical-rl]">Quick Apply</span>
      </button>

      {/* Backdrop + drawer stay mounted always (not just while `open`) so
          closing animates a slide-out/fade-out instead of instantly
          vanishing - an unmount at `open: false` would skip the transition
          entirely. Doesn't stop the tracked job from generating in the
          background either way; closing this is just hiding the panel,
          not cancelling anything. */}
      <div
        aria-hidden={!open}
        className={`fixed inset-0 z-40 bg-black/30 transition-opacity duration-300 ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
        onClick={() => setOpen(false)}
      />
      <div
        className={`fixed inset-y-0 right-0 z-50 flex w-96 flex-col border-l border-border bg-surface shadow-xl transition-transform duration-300 ease-out ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Zap size={15} className="text-accent" />
            Quick Apply
          </div>
          <div className="flex items-center gap-3">
            {trackedId === null && (
              <button
                type="button"
                onClick={() => {
                  setForm(EMPTY_FORM);
                  submitMutation.reset();
                }}
                disabled={submitMutation.isPending}
                aria-label="Reset"
                title="Reset"
                className="text-fg-muted transition-colors hover:text-fg disabled:opacity-40"
              >
                <RefreshCw size={15} />
              </button>
            )}
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close"
              className="text-fg-muted hover:text-fg"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
              {trackedId === null ? (
                <div className="flex flex-col gap-3">
                  <p className="text-xs text-fg-muted">
                    For a job that didn't come through Fetch - paste in what you have and generate a resume for it
                    right away.
                  </p>

                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs text-fg-muted">
                      Profile<span className="text-bad"> *</span>
                    </span>
                    <ProfileDropdown
                      profiles={profilesQuery.data ?? []}
                      value={form.profile}
                      onChange={(id) => setForm({ ...form, profile: id })}
                      className="w-full"
                    />
                  </label>

                  <Field
                    label="Company"
                    required
                    value={form.company}
                    onChange={(v) => setForm({ ...form, company: v })}
                  />
                  <Field
                    label="Job title"
                    required
                    value={form.title}
                    onChange={(v) => setForm({ ...form, title: v })}
                  />
                  <Field
                    label="Source"
                    placeholder="e.g. Recruiter email, LinkedIn message"
                    value={form.source}
                    onChange={(v) => setForm({ ...form, source: v })}
                  />
                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs text-fg-muted">Post date</span>
                    <DatePicker value={form.posted_at} onChange={(v) => setForm({ ...form, posted_at: v })} />
                  </label>
                  <Field
                    label="JD link"
                    required
                    placeholder="https://…"
                    value={form.url}
                    onChange={(v) => setForm({ ...form, url: v })}
                  />
                  <label className="flex flex-col gap-1.5">
                    <span className="text-xs text-fg-muted">
                      Description<span className="text-bad"> *</span>
                    </span>
                    <textarea
                      value={form.description}
                      onChange={(e) => setForm({ ...form, description: e.target.value })}
                      rows={10}
                      placeholder="Paste the job description here"
                      className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
                    />
                  </label>

                  {submitMutation.isSuccess && submitMutation.data.duplicate && (
                    <p className="animate-fade-in-up text-sm text-bad">
                      Already applied-to or already in the queue for this profile - not added again.
                    </p>
                  )}
                  {submitMutation.isError && (
                    <p className="animate-fade-in-up text-sm text-bad">Couldn't add that - check the backend and try again.</p>
                  )}

                  <Button
                    variant="primary"
                    disabled={!canSubmit || submitMutation.isPending}
                    onClick={() => submitMutation.mutate()}
                    className="mt-1 w-full justify-center py-2"
                  >
                    {submitMutation.isPending ? "Starting…" : "Generate resume"}
                  </Button>
                </div>
              ) : (
                <div className="flex flex-col gap-3">
                  <p className="text-xs text-fg-muted">
                    Tracking this one job - Quick Apply only ever follows one at a time.
                  </p>

                  <div className="rounded-md border border-border p-3">
                    <div className="font-medium">{trackedRow?.company ?? form.company}</div>
                    <div className="text-sm text-fg-muted">{trackedRow?.title ?? form.title}</div>
                    <div className="mt-2 flex items-center gap-2">
                      <StatusBadge status={trackedRow?.status ?? "generating"} />
                      {trackedRow?.error && (
                        <span
                          className={`text-xs ${trackedRow.status === "failed" ? "text-bad" : "text-fg-muted"}`}
                        >
                          {trackedRow.error}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex gap-2">
                    {trackedRow?.status === "ready" && (
                      <Button
                        variant="primary"
                        disabled={appliedMutation.isPending}
                        onClick={() => trackedId && appliedMutation.mutate(trackedId)}
                      >
                        <Check size={14} />
                        Mark applied
                      </Button>
                    )}
                    {trackedRow?.status === "ready" && trackedRow.staging_dir && (
                      <Button variant="secondary" onClick={() => trackedId && openFolder(trackedId)}>
                        <FolderOpen size={14} />
                        Open folder
                      </Button>
                    )}
                    {trackedRow?.status === "failed" && (
                      <Button
                        variant="secondary"
                        disabled={retryMutation.isPending}
                        onClick={() => trackedId && retryMutation.mutate(trackedId)}
                      >
                        <RotateCcw size={14} />
                        Retry
                      </Button>
                    )}
                    <Button
                      variant="danger"
                      disabled={removeMutation.isPending}
                      onClick={() => trackedId && removeMutation.mutate(trackedId)}
                    >
                      <Trash2 size={14} />
                      Remove
                    </Button>
                  </div>

                  <Button variant="ghost" onClick={backToForm}>
                    + New Quick Apply
                  </Button>
                </div>
              )}
            </div>
          </div>
    </>
  );
}
