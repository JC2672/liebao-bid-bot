import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

type ThemeChoice = "light" | "dark";

function systemPrefersDark() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function readStoredTheme(): ThemeChoice | null {
  const saved = localStorage.getItem("theme");
  return saved === "light" || saved === "dark" ? saved : null;
}

/** Toggles between light and dark, overriding the OS preference (see the
 * pre-paint script in index.html and the CSS in index.css). Starts from
 * whatever's currently in effect - the saved override if there is one,
 * otherwise the OS setting - so the very first click always visibly
 * flips something rather than possibly matching what's already shown.
 *
 * A sliding switch rather than a plain icon button - the track itself
 * carries the on/off state at a glance (which an icon swap alone doesn't),
 * and the thumb's icon still shows which mode is current. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeChoice>(
    () => readStoredTheme() ?? (systemPrefersDark() ? "dark" : "light"),
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  const isDark = theme === "dark";

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isDark}
      onClick={() => setTheme(isDark ? "light" : "dark")}
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      title={isDark ? "Switch to light mode" : "Switch to dark mode"}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors ${
        isDark ? "border-accent bg-accent" : "border-border bg-surface-hover"
      }`}
    >
      <span
        className={`inline-flex h-5 w-5 items-center justify-center rounded-full bg-surface shadow transition-transform ${
          isDark ? "translate-x-[22px]" : "translate-x-0.5"
        }`}
      >
        {isDark ? <Moon size={11} className="text-accent" /> : <Sun size={11} className="text-warn" />}
      </span>
    </button>
  );
}
