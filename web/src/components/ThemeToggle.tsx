import { useEffect, useState } from "react";

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
 * flips something rather than possibly matching what's already shown. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeChoice>(
    () => readStoredTheme() ?? (systemPrefersDark() ? "dark" : "light"),
  );

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  return (
    <button
      onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className="rounded-md border border-border p-1.5 text-fg-muted transition-colors hover:text-fg hover:bg-surface-hover"
    >
      {theme === "dark" ? (
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path d="M10 3a1 1 0 011 1v1a1 1 0 11-2 0V4a1 1 0 011-1zm0 12a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zm7-5a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zm10.657-5.657a1 1 0 010 1.414l-.707.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM6.464 14.243a1 1 0 010 1.414l-.707.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zm9.193 1.414a1 1 0 01-1.414 0l-.707-.707a1 1 0 111.414-1.414l.707.707a1 1 0 010 1.414zM6.464 5.757a1 1 0 01-1.414 0l-.707-.707a1 1 0 011.414-1.414l.707.707a1 1 0 010 1.414zM10 6a4 4 0 100 8 4 4 0 000-8z" />
        </svg>
      ) : (
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
        </svg>
      )}
    </button>
  );
}
