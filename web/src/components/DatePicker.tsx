import { useEffect, useRef, useState } from "react";
import { Calendar, ChevronLeft, ChevronRight } from "lucide-react";

function toISO(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function parseISO(s: string) {
  const [y, m, d] = s.split("-").map(Number);
  return y && m && d ? new Date(y, m - 1, d) : null;
}

const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];

/** A popover calendar in place of the browser's native `<input type="date">`,
 * matching ProfileDropdown's button+floating-panel pattern instead of the
 * native control's unstyled OS-level popup - the rest of this app doesn't
 * use native form controls for anything this visible. `value`/`onChange`
 * are plain ISO ("YYYY-MM-DD") strings, same as a native date input, so it
 * drops in anywhere one would. */
export function DatePicker({
  value,
  onChange,
  placeholder = "Select date",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const selected = value ? parseISO(value) : null;
  const [viewMonth, setViewMonth] = useState(() => selected ?? new Date());
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    setViewMonth(selected ?? new Date());
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const firstOfMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth(), 1);
  const daysInMonth = new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 0).getDate();
  const leadingBlanks = firstOfMonth.getDay();
  const today = new Date();

  const cells: (Date | null)[] = [
    ...Array.from({ length: leadingBlanks }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(viewMonth.getFullYear(), viewMonth.getMonth(), i + 1)),
  ];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center justify-between gap-2 rounded-md border border-border bg-surface px-2.5 py-1.5 text-left text-sm outline-none transition-colors hover:bg-surface-hover focus:border-accent"
      >
        <span className={selected ? "" : "text-fg-muted"}>
          {selected ? selected.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" }) : placeholder}
        </span>
        <Calendar size={14} className="shrink-0 text-fg-muted" />
      </button>

      {open && (
        <div className="animate-scale-in absolute left-0 z-10 mt-1 w-64 rounded-md border border-border bg-surface p-3 shadow-lg">
          <div className="mb-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() => setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() - 1, 1))}
              className="rounded p-1 text-fg-muted hover:bg-surface-hover hover:text-fg"
              aria-label="Previous month"
            >
              <ChevronLeft size={14} />
            </button>
            <span className="text-sm font-medium">
              {viewMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
            </span>
            <button
              type="button"
              onClick={() => setViewMonth(new Date(viewMonth.getFullYear(), viewMonth.getMonth() + 1, 1))}
              className="rounded p-1 text-fg-muted hover:bg-surface-hover hover:text-fg"
              aria-label="Next month"
            >
              <ChevronRight size={14} />
            </button>
          </div>

          <div className="grid grid-cols-7 gap-y-1 text-center">
            {WEEKDAYS.map((w, i) => (
              <span key={i} className="text-[11px] text-fg-muted">
                {w}
              </span>
            ))}
            {cells.map((day, i) => {
              if (!day) return <span key={i} />;
              const isSelected = selected && toISO(day) === toISO(selected);
              const isToday = toISO(day) === toISO(today);
              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => {
                    onChange(toISO(day));
                    setOpen(false);
                  }}
                  className={`mx-auto flex h-7 w-7 items-center justify-center rounded-full text-xs transition-colors ${
                    isSelected
                      ? "bg-accent text-accent-fg"
                      : isToday
                        ? "text-accent hover:bg-accent-wash"
                        : "hover:bg-surface-hover"
                  }`}
                >
                  {day.getDate()}
                </button>
              );
            })}
          </div>

          {value && (
            <button
              type="button"
              onClick={() => {
                onChange("");
                setOpen(false);
              }}
              className="mt-2 w-full rounded-md py-1 text-xs text-fg-muted hover:bg-surface-hover hover:text-fg"
            >
              Clear
            </button>
          )}
        </div>
      )}
    </div>
  );
}
