import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";

/** A labeled text input, shared by Profiles' and Fields' edit forms (was
 * duplicated identically in both before). `hint`, if given, renders as a
 * small muted line below the input - for explaining what a setting does
 * without cramming that explanation into the label itself, which reads
 * like a code comment stapled onto a form field rather than UI copy.
 * `secret`, if set, masks the value like a password field with a show/hide
 * toggle - for values like Sheet secret that shouldn't be visible by
 * default but still need to be checkable without retyping them. */
export function Field({
  label,
  value,
  onChange,
  placeholder,
  hint,
  secret,
  required,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  hint?: string;
  secret?: boolean;
  required?: boolean;
}) {
  const [revealed, setRevealed] = useState(false);

  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs text-fg-muted">
        {label}
        {required && <span className="text-bad"> *</span>}
      </span>
      <div className="relative">
        <input
          type={secret && !revealed ? "password" : "text"}
          value={value}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          className={`w-full rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none focus:border-accent ${
            secret ? "pr-8" : ""
          }`}
        />
        {secret && (
          <button
            type="button"
            onClick={() => setRevealed((r) => !r)}
            aria-label={revealed ? "Hide value" : "Show value"}
            title={revealed ? "Hide value" : "Show value"}
            className="absolute inset-y-0 right-2 flex items-center text-fg-muted hover:text-fg"
          >
            {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        )}
      </div>
      {hint && <span className="text-xs text-fg-muted/70">{hint}</span>}
    </label>
  );
}
