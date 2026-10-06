import { useEffect, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, GripVertical, Minus, Sparkles, X } from "lucide-react";
import { getQueueProgress, listProfiles } from "../lib/api";
import { formatDuration } from "../lib/format";

const STORAGE_KEY = "liebao-generation-widget-pos";

// A self-contained data-URI image, not a same-document element reference
// (`feImage href="#id"`) - confirmed live that the latter rasterizes as
// blank when the filter runs via CSS backdrop-filter on an HTML element
// rather than natively on SVG content, which made two different
// displacement-map techniques both silently no-op down to "just blur."
// An image resource reference doesn't depend on that live-render step.
function gradientDataUri(direction: "x" | "y") {
  const x2 = direction === "x" ? "100%" : "0%";
  const y2 = direction === "x" ? "0%" : "100%";
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">` +
    `<defs><linearGradient id="g" x1="0%" y1="0%" x2="${x2}" y2="${y2}">` +
    `<stop offset="0%" stop-color="#000000"/>` +
    `<stop offset="50%" stop-color="#808080"/>` +
    `<stop offset="100%" stop-color="#ffffff"/>` +
    `</linearGradient></defs>` +
    `<rect width="100" height="100" fill="url(#g)"/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function loadStoredPos(): { x: number; y: number } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (typeof parsed?.x === "number" && typeof parsed?.y === "number") return parsed;
  } catch {
    // per-viewer convenience only - a blocked/cleared store just means it
    // opens in the default corner again next time, nothing worth surfacing
  }
  return null;
}

// Label and value share one font (both sans, weight is the only
// difference) - a separate monospace face for the value read as visual
// noise here rather than the "label vs. data" distinction it's used for
// in the app's real tables, confirmed on the user's own review. Colors
// are theme tokens (`text-fg`/`text-fg-muted`), not a fixed light shade -
// now that the panel itself is neutral glass rather than a solid accent
// fill, the text has to track light/dark mode the same way the rest of
// the app already does, or it'd go low-contrast in one of the two.
function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-1.5">
      <span className="text-fg-muted">{label}</span>
      <span className="font-medium text-fg">{value}</span>
    </div>
  );
}

/** A floating, draggable status HUD - mounted once at the App level (not
 * inside the Queue tab) since generation keeps running in the background
 * regardless of which tab is active, and the whole point is to still see
 * it either way.
 *
 * The panel itself is the real Apple "Liquid Glass" material, not a
 * tinted color block - confirmed across two earlier passes that any flat
 * or accent-colored fill read as inert chrome rather than an active
 * overlay. The actual recipe (backdrop-blur + backdrop-saturate + a
 * mostly-neutral translucent tint + a thin light edge) is the same one
 * macOS/iOS panels use: blur is what sells "floating on top of the page"
 * (whatever's underneath visibly distorts through it while dragging),
 * saturation keeps that blurred content from looking washed-out grey, and
 * the light inset border simulates the glass edge catching light, visible
 * in both themes since it's a fixed highlight rather than a theme token.
 * The accent color is spent in exactly one place on top of it - the
 * progress bar's fill - rather than smeared across the whole panel.
 *
 * The profile isn't a row anymore - it's a small tag overlapping the
 * panel's own top-left corner, like a label tab, freeing the content
 * area for the numbers that actually change. Rows and their ready/failed/
 * cancelled outcome are merged into one progress bar with the counts
 * sitting above its right (leading) edge - one glance at the fill level
 * says "how far along," the label next to it spells out the numbers.
 *
 * Can't be closed while a run is active, by design, and stays up
 * indefinitely once finished until the user actually clicks the close
 * button - nothing times it out on its own. */
export function GenerationStatusWidget() {
  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: listProfiles });
  const progressQuery = useQuery({
    queryKey: ["generation-progress"],
    queryFn: () => getQueueProgress(),
    refetchInterval: 5000,
  });
  const progress = progressQuery.data;

  const justFinished = !progress?.active && !!progress?.finished_at;

  const [dismissed, setDismissed] = useState(false);
  // A fresh run always re-shows the widget even if a previous one was
  // dismissed - only this run's own completion/dismissal silences it.
  useEffect(() => {
    if (progress?.active) setDismissed(false);
  }, [progress?.active]);

  // Smooth client-side tick between polls - elapsed/remaining would
  // otherwise only move once every 5s poll, which reads as stuck rather
  // than live. Safe to use the browser's own clock for this (unlike the
  // pace average itself, see generation.py's own now()-leak writeup) -
  // this never feeds back into any calculation, it only decides how often
  // the already-computed numbers get re-rendered.
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (!progress?.active) return;
    const id = setInterval(() => forceTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [progress?.active]);

  const [pos, setPos] = useState<{ x: number; y: number } | null>(() => loadStoredPos());
  const dragOffset = useRef<{ x: number; y: number } | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  function onHeaderPointerDown(e: PointerEvent<HTMLDivElement>) {
    // Confirmed live as the cause of the close button not working: this
    // handler used to capture the pointer unconditionally, including when
    // the press actually landed on the close button (a child of this same
    // header) - once captured, the button's own click never fired. Letting
    // a press that originated inside any button skip drag-start entirely
    // fixes it.
    if ((e.target as HTMLElement).closest("button")) return;
    const rect = boxRef.current?.getBoundingClientRect();
    if (!rect) return;
    dragOffset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    e.currentTarget.setPointerCapture(e.pointerId);
  }
  function onHeaderPointerMove(e: PointerEvent<HTMLDivElement>) {
    if (!dragOffset.current) return;
    setPos({ x: e.clientX - dragOffset.current.x, y: e.clientY - dragOffset.current.y });
  }
  function onHeaderPointerUp() {
    dragOffset.current = null;
    setPos((current) => {
      if (current) {
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
        } catch {
          // per-viewer convenience only
        }
      }
      return current;
    });
  }

  if (!progress || (!progress.active && !justFinished) || dismissed) return null;

  const profileName = profilesQuery.data?.find((p) => p.id === progress.profile)?.name ?? progress.profile ?? "—";
  const elapsedSeconds = progress.started_at
    ? (Date.now() - new Date(progress.started_at).getTime()) / 1000
    : null;
  const expectedDoneAt = progress.eta_seconds !== null ? new Date(Date.now() + progress.eta_seconds * 1000) : null;
  const pct = progress.total > 0 ? (progress.completed / progress.total) * 100 : 0;

  return (
    <>
      {/* The actual refraction. A first pass used feTurbulence noise as
          the displacement source - that gives a uniform "frosted wobble"
          everywhere, not a believable lens, and read as barely-there on
          review. Rebuilt on the real technique behind the convincing
          liquid-glass demos: two linear gradients, one left-to-right and
          one top-to-bottom, recombined (R channel from the X gradient, G
          from the Y gradient) into one displacement map. Because each
          gradient runs dark-to-light across the panel, pixels on the left
          get pushed further left and the right further right, top further
          up and bottom further down - the backdrop bulges outward from
          the center the way light actually bends through a magnifying
          dome, rather than jittering in place. `color-interpolation-
          filters="sRGB"` keeps the gradient's color math in the space the
          values were actually authored in - browsers default this to
          linearRGB, which skews the displacement curve unless overridden.
          Only referenced by the `.glass-refract` CSS class (index.css)
          via `url(#...)` inside backdrop-filter. */}
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
        <filter
          id="liebao-glass-distortion"
          x="-10%"
          y="-10%"
          width="120%"
          height="120%"
          colorInterpolationFilters="sRGB"
        >
          <feImage href={gradientDataUri("x")} result="mapX" x="0" y="0" width="100%" height="100%" preserveAspectRatio="none" />
          <feImage href={gradientDataUri("y")} result="mapY" x="0" y="0" width="100%" height="100%" preserveAspectRatio="none" />
          {/* Keep just R from mapX and just G from mapY (zeroing the rest),
              then add the two - that's what lands both gradients in one
              image as the two channels feDisplacementMap actually reads. */}
          <feColorMatrix
            in="mapX"
            type="matrix"
            values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0 1"
            result="mapXr"
          />
          <feColorMatrix
            in="mapY"
            type="matrix"
            values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 0 1"
            result="mapYg"
          />
          <feComposite in="mapXr" in2="mapYg" operator="arithmetic" k2="1" k3="1" result="displacementMap" />
          <feGaussianBlur in="SourceGraphic" stdDeviation="8" result="blurredSource" />
          <feDisplacementMap
            in="blurredSource"
            in2="displacementMap"
            scale="170"
            xChannelSelector="R"
            yChannelSelector="G"
          />
        </filter>
      </svg>
      <div
        ref={boxRef}
        className="animate-scale-in fixed z-40 w-56"
        style={pos ? { left: pos.x, top: pos.y } : { bottom: 16, right: 16 }}
      >
      {/* The profile tag - sits half outside the glass panel below, tab-
          style, so it needs its own layer above the panel's own
          overflow-hidden (which clips the blur/gradient to its rounded
          corners) rather than living inside it. */}
      <span className="absolute -top-2 left-3 z-10 rounded-full bg-accent px-2 py-0.5 text-[10px] font-medium text-accent-fg shadow-sm">
        {profileName}
      </span>

      <div className="glass-refract overflow-hidden rounded-[22px] border border-white/25 bg-surface/50 text-fg shadow-[0_16px_40px_-10px_rgba(0,0,0,0.35)]">
        <div
          onPointerDown={onHeaderPointerDown}
          onPointerMove={onHeaderPointerMove}
          onPointerUp={onHeaderPointerUp}
          className="flex cursor-grab items-center gap-1.5 border-b border-border/50 px-2.5 pb-1.5 pt-3 text-sm select-none active:cursor-grabbing"
        >
          <GripVertical size={13} className="shrink-0 text-fg-muted/70" />
          {progress.active ? (
            <Sparkles size={13} className="shrink-0 animate-pulse text-accent" />
          ) : (
            <Check size={13} className="shrink-0 text-good" />
          )}
          <span className="flex-1 truncate font-medium">{progress.active ? "Generating" : "Finished"}</span>
          {!progress.active && (
            <button
              type="button"
              onClick={() => setDismissed(true)}
              aria-label="Dismiss"
              className="shrink-0 text-fg-muted hover:text-fg"
            >
              <X size={13} />
            </button>
          )}
        </div>

        <div className="flex flex-col gap-1.5 px-2.5 py-2 text-xs">
          {/* Rows + outcome, merged into one: the fill level IS "how far
              along," the counts above its right edge spell out the exact
              numbers behind it. "Resumes" names what's actually being
              counted - plain language over an internal term like
              "opportunities"/"jobs". */}
          <div>
            <div className="mb-1 flex items-center justify-between gap-1.5 text-[11px]">
              <span className="text-fg-muted">Resumes</span>
              <span className="flex items-center gap-1.5">
                <span className="font-medium text-fg">
                  {progress.completed}/{progress.total}
                </span>
                {progress.ready > 0 && (
                  <span className="inline-flex items-center gap-0.5 text-good">
                    <Check size={9} />
                    {progress.ready}
                  </span>
                )}
                {progress.failed > 0 && (
                  <span className="inline-flex items-center gap-0.5 text-bad">
                    <X size={9} />
                    {progress.failed}
                  </span>
                )}
                {progress.cancelled > 0 && (
                  <span className="inline-flex items-center gap-0.5 text-fg-muted">
                    <Minus size={9} />
                    {progress.cancelled}
                  </span>
                )}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-fg/10">
              <div
                className="h-full rounded-full bg-accent transition-[width] duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>

          {progress.active ? (
            <>
              <Row label="Elapsed" value={elapsedSeconds !== null ? formatDuration(elapsedSeconds) : "—"} />
              <Row
                label="Remaining"
                value={progress.eta_seconds !== null ? `~${formatDuration(progress.eta_seconds)}` : "estimating…"}
              />
              <Row
                label="Done by"
                value={
                  expectedDoneAt
                    ? `~${expectedDoneAt.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}`
                    : "—"
                }
              />
            </>
          ) : (
            <Row
              label="Took"
              value={progress.total_elapsed_seconds !== null ? formatDuration(progress.total_elapsed_seconds) : "—"}
            />
          )}
        </div>
      </div>
    </div>
    </>
  );
}
