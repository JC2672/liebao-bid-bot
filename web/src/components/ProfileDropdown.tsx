import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";

// A custom-styled profile picker matching FetchPage's ExportMenu pattern,
// in place of a native <select> - the rest of this app doesn't use native
// form controls for anything this visible. Shared between QueuePage and
// FetchPage rather than duplicated.
export function ProfileDropdown({
  profiles,
  value,
  onChange,
  disabled,
}: {
  profiles: { id: string; name: string }[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = profiles.find((p) => p.id === value);

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className="flex w-56 items-center justify-between gap-2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-sm outline-none transition-colors hover:bg-surface-hover focus:border-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span className="truncate">{selected?.name ?? "Select profile"}</span>
        <ChevronDown
          size={14}
          className={`shrink-0 text-fg-muted transition-transform duration-150 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="animate-scale-in absolute left-0 z-10 mt-1 w-56 overflow-hidden rounded-md border border-border bg-surface shadow-lg">
          {profiles.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => {
                onChange(p.id);
                setOpen(false);
              }}
              className={`block w-full px-3 py-2 text-left text-sm hover:bg-surface-hover ${
                p.id === value ? "bg-accent-wash text-accent" : ""
              }`}
            >
              {p.name}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
