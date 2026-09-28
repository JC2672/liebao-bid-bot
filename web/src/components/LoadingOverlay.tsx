import { useEffect, useState } from "react";
import { sourceIconUrl } from "../lib/api";

const CYCLE_MS = 500;

/** Full-page overlay shown while a fetch is running: a spinning ring with
 * the selected sources' favicons cycling in its center, so it's obvious
 * something is happening (a multi-source fetch can take a while) and which
 * sites are actually being hit. */
export function LoadingOverlay({ domains }: { domains: string[] }) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    setIndex(0);
    if (domains.length <= 1) return;
    const id = setInterval(() => {
      setIndex((i) => (i + 1) % domains.length);
    }, CYCLE_MS);
    return () => clearInterval(id);
  }, [domains]);

  const domain = domains[index] ?? domains[0];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg/80 backdrop-blur-sm">
      <div className="relative flex h-24 w-24 items-center justify-center">
        <div className="absolute inset-0 animate-spin rounded-full border-4 border-border border-t-accent" />
        {domain && (
          <img
            key={domain}
            src={sourceIconUrl(domain)}
            alt=""
            className="h-8 w-8 rounded-sm"
            onError={(e) => {
              e.currentTarget.style.visibility = "hidden";
            }}
          />
        )}
      </div>
      <p className="sr-only">Fetching…</p>
    </div>
  );
}
