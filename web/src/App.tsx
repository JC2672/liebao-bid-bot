import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FetchPage } from "./pages/FetchPage";
import { QueuePage } from "./pages/QueuePage";
import { ProfilesPage } from "./pages/ProfilesPage";
import { TemplatesPage } from "./pages/TemplatesPage";
import { ThemeToggle } from "./components/ThemeToggle";

const queryClient = new QueryClient();

type Tab = "fetch" | "queue" | "profiles" | "templates";

const TABS: [Tab, string][] = [
  ["fetch", "Fetch"],
  ["queue", "Queue"],
  ["profiles", "Profiles"],
  ["templates", "Templates"],
];

function App() {
  const [tab, setTab] = useState<Tab>("fetch");

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-bg text-fg">
        <header className="border-b border-border bg-surface">
          <div className="mx-auto flex max-w-7xl items-center gap-8 px-6">
            <div className="flex items-center gap-2 py-3">
              <img src="/logo.png" alt="" className="logo-light h-8 w-8 object-contain" />
              <img src="/brand/logo-white.png" alt="" className="logo-dark h-8 w-8 object-contain" />
              <span className="font-mono text-sm font-medium tracking-tight text-fg">
                liebao-bid-bot
              </span>
            </div>
            <nav className="flex h-full gap-6">
              {TABS.map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`border-b-2 py-4 text-sm font-medium transition-colors ${
                    tab === id
                      ? "border-accent text-fg"
                      : "border-transparent text-fg-muted hover:text-fg"
                  }`}
                >
                  {label}
                </button>
              ))}
            </nav>
            <div className="ml-auto py-3">
              <ThemeToggle />
            </div>
          </div>
        </header>

        {/*
          Every tab stays mounted; only visibility toggles. Fetch results, in
          particular, are that page's own local state (see FetchPage) - if
          the page unmounted on tab switch, the fetched list would silently
          vanish and reappear empty on return, which is exactly the bug this
          fixes.
        */}
        <main className="mx-auto max-w-7xl px-6 py-6">
          <div hidden={tab !== "fetch"}>
            <FetchPage />
          </div>
          <div hidden={tab !== "queue"}>
            <QueuePage active={tab === "queue"} />
          </div>
          <div hidden={tab !== "profiles"}>
            <ProfilesPage />
          </div>
          <div hidden={tab !== "templates"}>
            <TemplatesPage />
          </div>
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;
