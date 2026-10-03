import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Settings } from "lucide-react";
import { FetchPage } from "./pages/FetchPage";
import { QueuePage } from "./pages/QueuePage";
import { SetupPage } from "./pages/SetupPage";
import { ThemeToggle } from "./components/ThemeToggle";

const queryClient = new QueryClient();

type Tab = "fetch" | "queue" | "setup";

// Setup isn't a daily-use tab the way Fetch/Queue are - it's configuration
// you visit occasionally, so it sits apart at the header's far end as an
// icon rather than competing for space in the main text-label nav.
const TABS: [Tab, string][] = [
  ["fetch", "Fetch"],
  ["queue", "Queue"],
];

function App() {
  const [tab, setTab] = useState<Tab>("fetch");

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-bg text-fg">
        <header className="border-b border-border bg-surface">
          <div className="mx-auto flex max-w-7xl items-center gap-8 px-6">
            <div className="flex items-center gap-2 py-3">
              <img src="/logo.png" alt="" className="logo-light h-10 w-10 object-contain" />
              <img src="/brand/logo-white.png" alt="" className="logo-dark h-10 w-10 object-contain" />
              <img
                src="/brand/wordmark-black.png"
                alt="liebao-bid-bot"
                className="logo-light h-7 w-auto object-contain"
              />
              <img
                src="/brand/wordmark-white.png"
                alt="liebao-bid-bot"
                className="logo-dark h-7 w-auto object-contain"
              />
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
            <div className="ml-auto flex items-center gap-2 py-3">
              <button
                onClick={() => setTab("setup")}
                aria-label="Setup"
                title="Setup"
                className={`rounded-md border p-1.5 transition-colors ${
                  tab === "setup"
                    ? "border-accent bg-accent-wash text-accent"
                    : "border-border text-fg-muted hover:bg-surface-hover hover:text-fg"
                }`}
              >
                <Settings size={16} />
              </button>
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
          <div hidden={tab !== "setup"}>
            <SetupPage />
          </div>
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;
