import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import {
  createTemplate,
  deleteTemplate,
  getTemplate,
  listTemplates,
  templatePreviewUrl,
  updateTemplate,
  type Template,
  type TemplateInput,
} from "../lib/api";
import { Button, Card, IconButton } from "../components/ui";

const EMPTY_FORM: TemplateInput = { name: "", html: "" };

function TemplateCard({
  template,
  onEdit,
  onDelete,
  deletePending,
}: {
  template: Template;
  onEdit: () => void;
  onDelete: () => void;
  deletePending: boolean;
}) {
  return (
    <Card className="flex flex-col gap-2 overflow-hidden p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="font-medium">{template.name}</div>
        <div className="flex shrink-0 gap-1">
          <IconButton title="Edit" onClick={onEdit}>
            <Pencil size={14} />
          </IconButton>
          <IconButton title="Delete" tone="danger" disabled={deletePending} onClick={onDelete}>
            <Trash2 size={14} />
          </IconButton>
        </div>
      </div>

      {/* Scaled-down live preview (sample data, not a real profile) - lets you
          eyeball a template's look without opening the PDF for every tweak.
          The frame is a real US Letter ratio (8.5:11), not an arbitrary box -
          the iframe renders at Letter's actual pixel size (96dpi: 816x1056)
          and scales itself down to fit via a container-query unit, so it
          stays paper-shaped at any card width instead of a fixed px height
          that only happened to fit one column count. */}
      <a
        href={templatePreviewUrl(template.id, "pdf")}
        target="_blank"
        rel="noreferrer"
        className="relative block w-full overflow-hidden rounded border border-border bg-white"
        style={{ aspectRatio: "8.5 / 11", containerType: "inline-size" }}
        title="Open full PDF preview"
      >
        <iframe
          src={templatePreviewUrl(template.id, "html")}
          title={`${template.name} preview`}
          tabIndex={-1}
          className="pointer-events-none"
          style={{
            width: "816px",
            height: "1056px",
            transform: "scale(calc(100cqw / 816px))",
            transformOrigin: "top left",
          }}
        />
      </a>
    </Card>
  );
}

export function TemplatesPage() {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<TemplateInput>(EMPTY_FORM);

  const templatesQuery = useQuery({ queryKey: ["templates"], queryFn: listTemplates });

  const createMutation = useMutation({
    mutationFn: (input: TemplateInput) => createTemplate(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      setCreating(false);
      setForm(EMPTY_FORM);
    },
  });
  const updateMutation = useMutation({
    mutationFn: (input: TemplateInput) => updateTemplate(editingId!, input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["templates"] });
      // A live reference: every profile using this template renders
      // differently on its next generation as soon as this saves.
      setEditingId(null);
      setForm(EMPTY_FORM);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: deleteTemplate,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["templates"] }),
  });

  async function startEdit(t: Template) {
    const detail = await getTemplate(t.id);
    setForm({ name: detail.name, html: detail.html });
    setEditingId(t.id);
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
        <h2 className="text-sm font-semibold">Templates</h2>
        <Button variant="primary" onClick={startCreate}>
          + New Template
        </Button>
      </div>

      {templatesQuery.data?.length === 0 ? (
        <Card className="p-8 text-center text-sm text-fg-muted">
          No templates yet. Create one to give profiles a resume layout to reference.
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {templatesQuery.data?.map((t) => (
            <TemplateCard
              key={t.id}
              template={t}
              onEdit={() => startEdit(t)}
              deletePending={deleteMutation.isPending}
              onDelete={() => {
                if (confirm(`Delete template "${t.name}"? Profiles using it will need a new one.`)) {
                  deleteMutation.mutate(t.id);
                }
              }}
            />
          ))}
        </div>
      )}

      {deleteMutation.isError && (
        <p className="text-sm text-bad">
          {(deleteMutation.error as { response?: { data?: { detail?: string } } })?.response
            ?.data?.detail ?? "Failed to delete template."}
        </p>
      )}

      {isOpen && (
        <Card className="p-4">
          <h3 className="mb-3 text-sm font-semibold">{creating ? "New Template" : `Edit: ${editingId}`}</h3>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs text-fg-muted">Name</span>
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="w-72 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
            />
          </label>

          <label className="mt-3 flex flex-col gap-1.5">
            <span className="text-xs text-fg-muted">
              HTML (Jinja2 - rendered with resume_json plus the profile's contact fields, then printed to PDF)
            </span>
            <textarea
              value={form.html}
              onChange={(e) => setForm({ ...form, html: e.target.value })}
              rows={20}
              spellCheck={false}
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
            <Button variant="primary" disabled={pending || !form.name || !form.html} onClick={submit}>
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
