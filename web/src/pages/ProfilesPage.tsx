import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createProfile,
  deleteProfile,
  getProfile,
  listProfiles,
  updateProfile,
  type Profile,
  type ProfileInput,
} from "../lib/api";
import { Button, Card } from "../components/ui";

const EMPTY_FORM: ProfileInput = {
  id: "",
  name: "",
  title: "",
  location: "",
  phone: "",
  email: "",
  linkedin: "",
  sheet_id: "",
  sheet_tab: "",
  output_root: "",
  prompt: "",
};

function Field({
  label,
  value,
  onChange,
  placeholder,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-fg-muted">{label}</span>
      <input
        value={value}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-surface-hover px-2.5 py-1.5 text-sm outline-none focus:border-accent disabled:opacity-50"
      />
    </label>
  );
}

export function ProfilesPage() {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<ProfileInput>(EMPTY_FORM);

  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });

  const createMutation = useMutation({
    mutationFn: (input: ProfileInput) => createProfile(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      setCreating(false);
      setForm(EMPTY_FORM);
    },
  });
  const updateMutation = useMutation({
    mutationFn: (input: ProfileInput) => updateProfile(editingId!, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      setEditingId(null);
      setForm(EMPTY_FORM);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteProfile,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["profiles"] }),
  });

  async function startEdit(p: Profile) {
    const detail = await getProfile(p.id);
    setForm({
      id: detail.id, name: detail.name, title: detail.title, location: detail.location,
      phone: detail.phone, email: detail.email, linkedin: detail.linkedin,
      sheet_id: detail.sheet_id, sheet_tab: detail.sheet_tab, output_root: detail.output_root,
      prompt: detail.prompt,
    });
    setEditingId(p.id);
    setCreating(false);
  }

  function startCreate() {
    setForm(EMPTY_FORM);
    setCreating(true);
    setEditingId(null);
  }

  function cancel() {
    setCreating(false);
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  function submit() {
    if (creating) createMutation.mutate(form);
    else if (editingId) updateMutation.mutate(form);
  }

  const isOpen = creating || editingId !== null;
  const pending = createMutation.isPending || updateMutation.isPending;
  const error = createMutation.error || updateMutation.error;

  return (
    <div className="flex flex-col gap-4">
      <Card className="p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold">Profiles</h2>
          <Button variant="primary" onClick={startCreate}>
            + New Profile
          </Button>
        </div>

        <div className="flex flex-col divide-y divide-border">
          {profilesQuery.data?.map((p) => (
            <div key={p.id} className="flex items-center justify-between py-2.5">
              <div>
                <div className="font-medium">{p.name}</div>
                <div className="text-xs text-fg-muted">
                  {p.title || "—"} · Sheet tab: {p.sheet_tab} · {p.output_root}
                </div>
              </div>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => startEdit(p)}>
                  Edit
                </Button>
                <Button
                  variant="danger"
                  disabled={deleteMutation.isPending}
                  onClick={() => {
                    if (confirm(`Delete profile "${p.name}"? This cannot be undone.`)) {
                      deleteMutation.mutate(p.id);
                    }
                  }}
                >
                  Delete
                </Button>
              </div>
            </div>
          ))}
          {profilesQuery.data?.length === 0 && (
            <p className="py-8 text-center text-sm text-fg-muted">
              No profiles yet. Create one to start fetching and generating for it.
            </p>
          )}
        </div>

        {deleteMutation.isError && (
          <p className="mt-2 text-sm text-bad">
            {(deleteMutation.error as { response?: { data?: { detail?: string } } })?.response
              ?.data?.detail ?? "Failed to delete profile."}
          </p>
        )}
      </Card>

      {isOpen && (
        <Card className="p-4">
          <h3 className="mb-3 text-sm font-semibold">
            {creating ? "New Profile" : `Edit: ${editingId}`}
          </h3>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Full name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
            <Field
              label="Slug (id)"
              value={form.id ?? ""}
              disabled={!creating}
              placeholder="auto-generated from name if left blank"
              onChange={(v) => setForm({ ...form, id: v })}
            />
            <Field label="Resume title" value={form.title} onChange={(v) => setForm({ ...form, title: v })} />
            <Field label="Location" value={form.location} onChange={(v) => setForm({ ...form, location: v })} />
            <Field label="Phone" value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} />
            <Field label="Email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} />
            <Field label="LinkedIn" value={form.linkedin} onChange={(v) => setForm({ ...form, linkedin: v })} />
            <Field
              label="Output root (folder on disk)"
              value={form.output_root}
              placeholder="F:/Applications/Firstname"
              onChange={(v) => setForm({ ...form, output_root: v })}
            />
            <Field
              label="Google Sheet ID"
              value={form.sheet_id}
              placeholder="optional until Applied is used"
              onChange={(v) => setForm({ ...form, sheet_id: v })}
            />
            <Field label="Sheet tab name" value={form.sheet_tab} onChange={(v) => setForm({ ...form, sheet_tab: v })} />
          </div>

          <label className="mt-3 flex flex-col gap-1.5">
            <span className="text-xs text-fg-muted">Resume-tailoring prompt (JD is appended at generation time)</span>
            <textarea
              value={form.prompt}
              onChange={(e) => setForm({ ...form, prompt: e.target.value })}
              rows={8}
              className="rounded-md border border-border bg-surface-hover px-2.5 py-1.5 font-mono text-xs outline-none focus:border-accent"
            />
          </label>

          {error && (
            <p className="mt-2 text-sm text-bad">
              {(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
                "Save failed."}
            </p>
          )}

          <div className="mt-3 flex gap-2">
            <Button variant="primary" disabled={pending || !form.name || !form.sheet_tab || !form.output_root} onClick={submit}>
              {pending ? "Saving…" : "Save"}
            </Button>
            <Button variant="ghost" onClick={cancel}>
              Cancel
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
