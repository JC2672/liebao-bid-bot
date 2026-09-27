import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FetchPage } from "./pages/FetchPage";
import { QueuePage } from "./pages/QueuePage";
import { ProfilesPage } from "./pages/ProfilesPage";

const queryClient = new QueryClient();

type Tab = "fetch" | "queue" | "profiles";

const TABS: [Tab, string][] = [
  ["fetch", "Fetch"],
  ["queue", "Queue"],
  ["profiles", "Profiles"],
];

function App() {
  const [tab, setTab] = useState<Tab>("fetch");

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-bg text-fg">
        <header className="border-b border-border bg-surface">
          <div className="mx-auto flex max-w-7xl items-center gap-8 px-6">
            <span className="py-4 font-mono text-sm font-medium tracking-tight text-fg">
              liebao-bid-bot
            </span>
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
          </div>
        </header>

        <main className="mx-auto max-w-7xl px-6 py-6">
          {tab === "fetch" && <FetchPage />}
          {tab === "queue" && <QueuePage />}
          {tab === "profiles" && <ProfilesPage />}
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;
