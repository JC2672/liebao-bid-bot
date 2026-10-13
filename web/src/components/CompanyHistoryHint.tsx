import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { History } from "lucide-react";
import type { CompanyMatch } from "../lib/api";

function formatDate(raw: string) {
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? raw : d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/** The clock icon next to a Queue row's company name, for a company that
 * already showed up in the Applied sheet at import time (see
 * Opportunity.company_seen_detail) - hovering it shows exactly which past
 * application(s) it's flagging against (role/date/stage), not just a bare
 * "you've seen this company before" with no way to tell which one.
 *
 * Rendered through a portal into `document.body`, not as a normal child
 * of the icon - the icon lives inside a Queue row, and rows get a plain
 * CSS `opacity-50` while a generation batch has them dimmed/locked (see
 * QueuePage's `dimmed`). That opacity applies to every descendant's
 * rendered appearance regardless of `position: absolute`, so a popover
 * nested inside a dimmed row rendered translucent even though its own
 * background was fully opaque - confirmed live. Portaling it out from
 * under that ancestor is what actually fixes it, not any background/
 * opacity utility on the popover itself. */
export function CompanyHistoryHint({ matches }: { matches: CompanyMatch[] }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);
  const iconRef = useRef<HTMLSpanElement>(null);
  if (matches.length === 0) return null;

  function show() {
    const rect = iconRef.current?.getBoundingClientRect();
    if (rect) setPos({ left: rect.left + rect.width / 2, top: rect.bottom + 6 });
    setOpen(true);
  }

  return (
    <span
      ref={iconRef}
      className="relative inline-flex shrink-0"
      onMouseEnter={show}
      onMouseLeave={() => setOpen(false)}
    >
      <History size={14} className="cursor-default text-warn" />

      {open &&
        pos &&
        createPortal(
          <div
            className="animate-scale-in fixed z-50 w-72 -translate-x-1/2 rounded-md border border-warn/50 bg-surface p-2 text-left shadow-lg ring-1 ring-warn/15"
            style={{ left: pos.left, top: pos.top }}
          >
            <div className="mb-1.5 px-1 text-[11px] font-medium text-fg-muted">
              Already applied to this company {matches.length > 1 ? `(${matches.length}x)` : ""}
            </div>
            <div className="flex flex-col gap-1">
              {matches.map((m, i) => (
                <div key={i} className="rounded px-1.5 py-1 text-xs hover:bg-surface-hover">
                  <div className="font-medium text-fg">{m.title || "(no title on file)"}</div>
                  <div className="flex items-center gap-1.5 text-fg-muted">
                    <span>{m.date ? formatDate(m.date) : "unknown date"}</span>
                    {m.stage && (
                      <>
                        <span>•</span>
                        <span>{m.stage}</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>,
          document.body,
        )}
    </span>
  );
}
