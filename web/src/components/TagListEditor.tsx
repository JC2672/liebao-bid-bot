import { useState } from "react";
import { Plus, X } from "lucide-react";

/** A small reusable control for editing a list of strings interactively -
 * a text input + Add button, with each entry shown as a removable chip
 * below. Used three times on the field editor (title list, relevance
 * allow/deny keywords) - nothing in this app edited a list of strings
 * this way before, so there was no existing component to reuse. */
export function TagListEditor({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");

  function add() {
    const trimmed = draft.trim();
    if (!trimmed || value.includes(trimmed)) {
      setDraft("");
      return;
    }
    onChange([...value, trimmed]);
    setDraft("");
  }

  function remove(entry: string) {
    onChange(value.filter((v) => v !== entry));
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-fg-muted">{label}</span>
      <div className="flex gap-2">
        <input
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent"
        />
        <button
          type="button"
          onClick={add}
          aria-label={`Add to ${label}`}
          className="inline-flex items-center justify-center rounded-md border border-border bg-surface px-2.5 text-fg-muted transition-colors hover:bg-surface-hover hover:text-fg"
        >
          <Plus size={14} />
        </button>
      </div>
      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pt-1">
          {value.map((entry) => (
            <span
              key={entry}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-surface-hover px-2 py-0.5 text-xs"
            >
              {entry}
              <button
                type="button"
                onClick={() => remove(entry)}
                aria-label={`Remove ${entry}`}
                className="text-fg-muted hover:text-bad"
              >
                <X size={12} />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
