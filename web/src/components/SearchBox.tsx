import { Search, X } from "lucide-react";

/** A small bordered search input with a leading icon and a clear button
 * that only appears once there's something to clear - shared by Fetch's
 * results table and Queue, both of which search across company + title. */
export function SearchBox({
  value,
  onChange,
  placeholder = "Search company or title…",
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={`relative ${className}`}>
      <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-muted" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-64 rounded-md border border-border bg-surface py-1.5 pl-8 pr-7 text-sm outline-none focus:border-accent"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label="Clear search"
          className="absolute right-2 top-1/2 -translate-y-1/2 text-fg-muted transition-colors hover:text-fg"
        >
          <X size={13} />
        </button>
      )}
    </div>
  );
}
