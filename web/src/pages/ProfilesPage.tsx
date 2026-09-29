import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail, MapPin, Pencil, Phone, Link2, Trash2 } from "lucide-react";
import {
  createProfile,
  deleteProfile,
  getProfile,
  listProfiles,
  listTemplates,
  pickFolder,
  updateProfile,
  type Profile,
  type ProfileInput,
} from "../lib/api";
import { Button, Card, IconButton } from "../components/ui";

// lucide-react has no brand/logo icons (dropped a while back) - confirmed
// by checking the installed package's exports directly rather than
// guessing a name like "Linkedin" exists, which crashed the whole page
// last time (an unresolved icon import renders as `undefined`, and React
// throws on mount rather than just showing a broken icon). Link2 (a plain
// chain-link glyph) stands in for "this is a link" generically.
function linkedinHref(value: string) {
  return /^https?:\/\//i.test(value) ? value : `https://${value}`;
}

function ProfileCard({
  profile,
  onEdit,
  onDelete,
  deletePending,
}: {
  profile: Profile;
  onEdit: () => void;
  onDelete: () => void;
  deletePending: boolean;
}) {
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium">{profile.name}</div>
        <div className="flex shrink-0 gap-1">
          <IconButton title="Edit" onClick={onEdit}>
            <Pencil size={14} />
          </IconButton>
          <IconButton title="Delete" tone="danger" disabled={deletePending} onClick={onDelete}>
            <Trash2 size={14} />
          </IconButton>
        </div>
      </div>

      <div className="flex flex-col gap-1.5 text-sm text-fg-muted">
        {profile.location && (
          <div className="flex items-center gap-2">
            <MapPin size={14} className="shrink-0" />
            <span className="truncate">{profile.location}</span>
          </div>
        )}
        {profile.phone && (
          <div className="flex items-center gap-2">
            <Phone size={14} className="shrink-0" />
            <span className="truncate">{profile.phone}</span>
          </div>
        )}
        {profile.email && (
          <div className="flex items-center gap-2">
            <Mail size={14} className="shrink-0" />
            <span className="truncate">{profile.email}</span>
          </div>
        )}
        {profile.linkedin && (
          <div className="flex items-center gap-2">
            <Link2 size={14} className="shrink-0" />
            <a
              href={linkedinHref(profile.linkedin)}
              target="_blank"
              rel="noreferrer"
              className="truncate hover:text-accent hover:underline"
            >
              {profile.linkedin}
            </a>
          </div>
        )}
        {!profile.location && !profile.phone && !profile.email && !profile.linkedin && (
          <span className="text-fg-muted/70">No contact details set</span>
        )}
      </div>
    </Card>
  );
}

const EMPTY_FORM: ProfileInput = {
  name: "",
  location: "",
  phone: "",
  email: "",
  linkedin: "",
  sheet_id: "",
  sheet_tab: "",
  output_root: "",
  template_id: "default",
  prompt: "",
};

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-fg-muted">{label}</span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
      />
    </label>
  );
}

export function ProfilesPage() {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<ProfileInput>(EMPTY_FORM);
  const [pickingFolder, setPickingFolder] = useState(false);

  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  const templatesQuery = useQuery({ queryKey: ["templates"], queryFn: listTemplates });

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
      name: detail.name, location: detail.location,
      phone: detail.phone, email: detail.email, linkedin: detail.linkedin,
      sheet_id: detail.sheet_id, sheet_tab: detail.sheet_tab, output_root: detail.output_root,
      template_id: detail.template_id,
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

  async function browseForOutputRoot() {
    setPickingFolder(true);
    try {
      const path = await pickFolder("Select the folder where this profile's applications are saved");
      if (path) setForm((f) => ({ ...f, output_root: path }));
    } finally {
      setPickingFolder(false);
    }
  }

  const isOpen = creating || editingId !== null;
  const pending = createMutation.isPending || updateMutation.isPending;
  const error = createMutation.error || updateMutation.error;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Profiles</h2>
        <Button variant="primary" onClick={startCreate}>
          + New Profile
        </Button>
      </div>

      {profilesQuery.data?.length === 0 ? (
        <Card className="p-8 text-center text-sm text-fg-muted">
          No profiles yet. Create one to start fetching and generating for it.
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {profilesQuery.data?.map((p) => (
            <ProfileCard
              key={p.id}
              profile={p}
              onEdit={() => startEdit(p)}
              deletePending={deleteMutation.isPending}
              onDelete={() => {
                if (confirm(`Delete profile "${p.name}"? This cannot be undone.`)) {
                  deleteMutation.mutate(p.id);
                }
              }}
            />
          ))}
        </div>
      )}

      {deleteMutation.isError && (
        <p className="text-sm text-bad">
          {(deleteMutation.error as { response?: { data?: { detail?: string } } })?.response
            ?.data?.detail ?? "Failed to delete profile."}
        </p>
      )}

      {isOpen && (
        <Card className="p-4">
          <h3 className="mb-3 text-sm font-semibold">{creating ? "New Profile" : `Edit: ${editingId}`}</h3>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Full name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
            <Field label="Location" value={form.location} onChange={(v) => setForm({ ...form, location: v })} />
            <Field label="Phone" value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} />
            <Field label="Email" value={form.email} onChange={(v) => setForm({ ...form, email: v })} />
            <Field label="LinkedIn" value={form.linkedin} onChange={(v) => setForm({ ...form, linkedin: v })} />
            <Field
              label="Google Sheet ID"
              value={form.sheet_id}
              placeholder="optional until Applied is used"
              onChange={(v) => setForm({ ...form, sheet_id: v })}
            />
            <Field label="Sheet tab name" value={form.sheet_tab} onChange={(v) => setForm({ ...form, sheet_tab: v })} />

            <label className="flex flex-col gap-1.5">
              <span className="text-xs text-fg-muted">Output root (folder on disk)</span>
              <div className="flex gap-2">
                <input
                  value={form.output_root}
                  readOnly
                  placeholder="Click Browse to choose a folder"
                  className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm text-fg-muted outline-none"
                />
                <Button variant="secondary" disabled={pickingFolder} onClick={browseForOutputRoot}>
                  {pickingFolder ? "Waiting…" : "Browse…"}
                </Button>
              </div>
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-xs text-fg-muted">Template</span>
              <select
                value={form.template_id}
                onChange={(e) => setForm({ ...form, template_id: e.target.value })}
                className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
              >
                {templatesQuery.data?.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="mt-3 flex flex-col gap-1.5">
            <span className="text-xs text-fg-muted">Resume-tailoring prompt (JD is appended at generation time)</span>
            <textarea
              value={form.prompt}
              onChange={(e) => setForm({ ...form, prompt: e.target.value })}
              rows={8}
              className="rounded-md border border-border bg-surface px-2.5 py-1.5 font-mono text-xs outline-none focus:border-accent"
            />
          </label>

          {error && (
            <p className="mt-2 text-sm text-bad">
              {(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
                "Save failed."}
            </p>
          )}

          <div className="mt-3 flex gap-2">
            <Button
              variant="primary"
              disabled={pending || !form.name || !form.sheet_tab || !form.output_root}
              onClick={submit}
            >
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
