import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, List, Pencil, Search, Trash2, XCircle } from "lucide-react";
import {
  createField,
  deleteField,
  getField,
  listFields,
  updateField,
  type FieldConfig,
  type FieldInput,
} from "../lib/api";
import { Badge, Button, Card, IconButton } from "../components/ui";
import { TagListEditor } from "../components/TagListEditor";

function FieldCard({
  field,
  onEdit,
  onDelete,
  deletePending,
}: {
  field: FieldConfig;
  onEdit: () => void;
  onDelete: () => void;
  deletePending: boolean;
}) {
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium">{field.name}</div>
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
        <div className="flex items-center gap-2">
          <Search size={14} className="shrink-0" />
          <span className="truncate font-mono text-xs text-fg">{field.query_term}</span>
        </div>
        <div className="flex items-center gap-2">
          <List size={14} className="shrink-0" />
          <span className="truncate">{field.title_list.length} title-list entries</span>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5 border-t border-border pt-3">
        <Badge tone="good">
          <CheckCircle2 size={12} className="mr-1 inline" />
          {field.relevance_allow.length} allow
        </Badge>
        <Badge tone="bad">
          <XCircle size={12} className="mr-1 inline" />
          {field.relevance_deny.length} deny
        </Badge>
      </div>
    </Card>
  );
}

const EMPTY_FORM: FieldInput = {
  name: "",
  query_term: "",
  title_list: [],
  relevance_allow: [],
  relevance_deny: [],
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

export function FieldsPage() {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<FieldInput>(EMPTY_FORM);

  const fieldsQuery = useQuery({ queryKey: ["fields"], queryFn: listFields });

  const createMutation = useMutation({
    mutationFn: (input: FieldInput) => createField(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fields"] });
      setCreating(false);
      setForm(EMPTY_FORM);
    },
  });
  const updateMutation = useMutation({
    mutationFn: (input: FieldInput) => updateField(editingId!, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["fields"] });
      setEditingId(null);
      setForm(EMPTY_FORM);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteField,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["fields"] }),
  });

  async function startEdit(f: FieldConfig) {
    const detail = await getField(f.id);
    setForm({
      name: detail.name, query_term: detail.query_term,
      title_list: detail.title_list, relevance_allow: detail.relevance_allow,
      relevance_deny: detail.relevance_deny,
    });
    setEditingId(f.id);
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
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">Fetch options - Fields</h2>
        <Button variant="primary" onClick={startCreate}>
          + New Field
        </Button>
      </div>

      {fieldsQuery.data?.length === 0 ? (
        <Card className="p-8 text-center text-sm text-fg-muted">
          No fields yet. Create one so a profile has a query term/title list/
          relevance keywords to fetch with.
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {fieldsQuery.data?.map((f) => (
            <FieldCard
              key={f.id}
              field={f}
              onEdit={() => startEdit(f)}
              deletePending={deleteMutation.isPending}
              onDelete={() => {
                if (confirm(`Delete field "${f.name}"? This cannot be undone.`)) {
                  deleteMutation.mutate(f.id);
                }
              }}
            />
          ))}
        </div>
      )}

      {deleteMutation.isError && (
        <p className="text-sm text-bad">
          {(deleteMutation.error as { response?: { data?: { detail?: string } } })?.response
            ?.data?.detail ?? "Failed to delete field."}
        </p>
      )}

      {isOpen && (
        <Card className="p-4">
          <h3 className="mb-3 text-sm font-semibold">{creating ? "New Field" : `Edit: ${editingId}`}</h3>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Name" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
            <Field
              label="Query term"
              value={form.query_term}
              placeholder="what sources that take free text search for"
              onChange={(v) => setForm({ ...form, query_term: v })}
            />
          </div>

          <div className="mt-3 flex flex-col gap-3">
            <TagListEditor
              label="Title list (for sources where a bare query term is a trap)"
              value={form.title_list}
              placeholder="e.g. Salesforce Developer"
              onChange={(v) => setForm({ ...form, title_list: v })}
            />
            <TagListEditor
              label="Relevance allow keywords (a posting's title must match one of these)"
              value={form.relevance_allow}
              placeholder="e.g. salesforce"
              onChange={(v) => setForm({ ...form, relevance_allow: v })}
            />
            <TagListEditor
              label="Relevance deny keywords (title must not match any of these)"
              value={form.relevance_deny}
              placeholder="e.g. account executive"
              onChange={(v) => setForm({ ...form, relevance_deny: v })}
            />
          </div>

          {error && (
            <p className="mt-2 text-sm text-bad">
              {(error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
                "Save failed."}
            </p>
          )}

          <div className="mt-3 flex gap-2">
            <Button variant="primary" disabled={pending || !form.name || !form.query_term} onClick={submit}>
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
