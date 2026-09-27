import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FetchPage } from "./pages/FetchPage";
import { QueuePage } from "./pages/QueuePage";

const queryClient = new QueryClient();

type Tab = "fetch" | "queue";

function App() {
  const [tab, setTab] = useState<Tab>("fetch");

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-bg text-fg">
        <header className="border-b border-border px-6 py-4">
          <div className="mx-auto flex max-w-6xl items-center gap-6">
            <h1 className="text-base font-semibold">liebao-bid-bot</h1>
            <nav className="flex gap-1">
              {(
                [
                  ["fetch", "Fetch"],
                  ["queue", "Queue"],
                ] as [Tab, string][]
              ).map(([id, label]) => (
                <button
                  key={id}
                  onClick={() => setTab(id)}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium ${
                    tab === id
                      ? "bg-accent/10 text-accent"
                      : "text-fg-muted hover:text-fg"
                  }`}
                >
                  {label}
                </button>
              ))}
            </nav>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-6 py-6">
          {tab === "fetch" ? <FetchPage /> : <QueuePage />}
        </main>
      </div>
    </QueryClientProvider>
  );
}

export default App;
