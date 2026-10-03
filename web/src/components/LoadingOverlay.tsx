import { Sparkle, X } from "lucide-react";
import { sourceIconUrl, type SourceProgress } from "../lib/api";

export interface LoadingOverlayRow extends SourceProgress {
  domain: string;
  label: string;
}

/** Overlay shown while a fetch is running, scoped to the results list area
 * beneath FetchPage's configuration panel (that panel disables its own
 * controls separately - see FetchPage) rather than the whole viewport or
 * even the whole page: the backend fetch itself already doesn't block
 * anything else (FastAPI runs its plain `def` handler in a thread pool,
 * not the main event loop, so other tabs' polling keeps working
 * underneath regardless), so there's no reason to block more of the UI
 * than "the list that doesn't exist yet."
 *
 * A literal checklist, not a decorative animation: every row's state here
 * comes straight from GET /fetch/status (see routers/fetch.py), which
 * tracks real per-source progress as the backend works through the list.
 * Deliberately floats directly on the overlay's own blurred backdrop - no
 * card border, no row dividers - so it reads as a quiet status list, not
 * a table.
 *
 * `pending` renders no icon at all (nothing has happened to that row yet,
 * so nothing claims to). `running` is a layered sparkle: a soft blurred
 * glow breathing behind it, the sparkle itself twinkling with a
 * drop-shadow bloom and a slow hue-rotate shimmer through its own color,
 * and a tiny second sparkle glinting at its corner on an offset beat - in
 * the spirit of Claude.ai's own "thinking" indicator (a living, glowing
 * thing) rather than a mechanical spinner; see .status-thinking-* in
 * index.css. `done` draws its checkmark stroke in over ~0.35s with a
 * small pop at the end, rather than simply appearing - see
 * .status-check-stroke/.status-check-pop in index.css.
 *
 * A checked-off row (done or failed) also strikes through its own label -
 * it's finished, not just visually ticked - and a "done" row shows how
 * many raw postings it actually returned (before dedupe/gating) right
 * next to the struck-through label; a "failed" source never produced a
 * real count, so none is shown for it.
 */
export function LoadingOverlay({ sources }: { sources: LoadingOverlayRow[] }) {
  const checked = sources.filter((s) => s.status === "done" || s.status === "failed").length;

  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 rounded-lg bg-bg/85 backdrop-blur-sm">
      <div className="flex flex-col gap-2.5">
        {sources.map((s) => {
          const isChecked = s.status === "done" || s.status === "failed";
          return (
            <div key={s.name} className="flex items-center gap-2.5">
              <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                <StatusIcon status={s.status} />
              </span>
              <img
                src={sourceIconUrl(s.domain)}
                alt=""
                className="h-4 w-4 shrink-0 rounded-sm"
                onError={(e) => {
                  e.currentTarget.style.visibility = "hidden";
                }}
              />
              <span
                className={`text-sm ${isChecked ? "line-through" : ""} ${
                  s.status === "failed" ? "text-bad" : s.status === "pending" ? "text-fg-muted" : "text-fg"
                }`}
              >
                {s.label}
              </span>
              {s.status === "done" && s.count !== null && (
                <span className="text-xs text-fg-muted">({s.count})</span>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-xs text-fg-muted">
        {checked} / {sources.length} checked
      </p>
    </div>
  );
}

function StatusIcon({ status }: { status: SourceProgress["status"] }) {
  if (status === "pending") return null;

  if (status === "running") {
    return (
      <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
        <span className="status-thinking-glow absolute inset-[-3px] rounded-full" />
        <Sparkle size={13} fill="currentColor" className="status-thinking-icon relative text-accent" />
        <Sparkle
          size={7}
          fill="currentColor"
          className="status-thinking-spark absolute -right-0.5 -top-0.5 text-accent"
        />
      </span>
    );
  }

  if (status === "failed") {
    return <X size={14} className="shrink-0 text-bad" />;
  }

  // done - a checkmark that draws itself in rather than just appearing.
  // `pathLength={1}` normalizes the path to length 1 regardless of its
  // actual geometry, so stroke-dasharray/dashoffset can animate 1 -> 0
  // without needing to hand-measure the path.
  return (
    <svg viewBox="0 0 24 24" width={14} height={14} fill="none" className="status-check-pop shrink-0 text-good">
      <path
        d="M4 12.5 L9.5 18 L20 6.5"
        pathLength={1}
        stroke="currentColor"
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="status-check-stroke"
      />
    </svg>
  );
}
