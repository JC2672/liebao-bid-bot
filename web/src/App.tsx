import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Settings } from "lucide-react";
import { FetchPage } from "./pages/FetchPage";
import { QueuePage } from "./pages/QueuePage";
import { SetupPage } from "./pages/SetupPage";
import { GenerationStatusWidget } from "./components/GenerationStatusWidget";
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

// The header used to scroll away with the page like any other block - fine
// when a tab's content fit on screen, but Fetch's results table and Queue's
// rows both run long, so the tab switcher/profile-independent controls up
// there could end up scrolled out of reach. Pinning it (`sticky`) fixes
// that; the shrink-on-scroll below is just this fix announcing itself - a
// static sticky header can otherwise read as "stuck/overlapping" rather
// than "intentionally staying put" the first time content slides under it.
function useScrolled(thresholdPx = 8) {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    function onScroll() {
      setScrolled(window.scrollY > thresholdPx);
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [thresholdPx]);
  return scrolled;
}

// Fetch/Queue used to switch with an instant border-color snap - no sense
// of motion between them at all. A sliding underline (measured off the
// actual buttons, so it still lines up if the label text or header font
// ever changes) reads as one indicator moving, not two states popping in
// and out. It hides itself (width 0) while Setup is active, since that tab
// lives outside this nav entirely.
function useTabIndicator(tab: Tab, tabRefs: React.RefObject<Partial<Record<Tab, HTMLButtonElement>>>) {
  const navRef = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState<{ left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    function measure() {
      const nav = navRef.current;
      const btn = tabRefs.current[tab];
      if (!nav || !btn) {
        setIndicator(null);
        return;
      }
      const navRect = nav.getBoundingClientRect();
      const btnRect = btn.getBoundingClientRect();
      setIndicator({ left: btnRect.left - navRect.left, width: btnRect.width });
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [tab, tabRefs]);

  return { navRef, indicator };
}

function App() {
  const [tab, setTab] = useState<Tab>("fetch");
  const scrolled = useScrolled();
  const tabRefs = useRef<Partial<Record<Tab, HTMLButtonElement>>>({});
  const { navRef, indicator } = useTabIndicator(tab, tabRefs);
  // Fetch and Queue each keep their own independent profile selection the
  // rest of the time (so reviewing one profile's Queue while fetching for
  // another still works) - this is the one deliberate exception: "Queue
  // after fetch" hands the job straight to Queue with no manual step in
  // between, so Queue needs to land on that same profile too, or the
  // newly-queued/generating rows are sitting there correct but invisible
  // behind whatever profile Queue's own dropdown happened to be on.
  const [queueFocusProfile, setQueueFocusProfile] = useState<string | undefined>();

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-bg text-fg">
        <header
          className={`sticky top-0 z-30 border-b border-border bg-surface transition-shadow duration-300 ${
            scrolled ? "shadow-md" : "shadow-none"
          }`}
        >
          <div className="mx-auto flex max-w-[1680px] items-center gap-8 px-8">
            <div
              className={`flex items-center gap-2 py-3 transition-[padding] duration-200 ${scrolled ? "!py-2" : ""}`}
            >
              <img
                src="/logo.png"
                alt=""
                className={`logo-light object-contain transition-all duration-200 ${
                  scrolled ? "h-7 w-7" : "h-10 w-10"
                }`}
              />
              <img
                src="/brand/logo-white.png"
                alt=""
                className={`logo-dark object-contain transition-all duration-200 ${
                  scrolled ? "h-7 w-7" : "h-10 w-10"
                }`}
              />
              <img
                src="/brand/wordmark-black.png"
                alt="liebao-bid-bot"
                className={`logo-light w-auto object-contain transition-all duration-200 ${
                  scrolled ? "h-5" : "h-7"
                }`}
              />
              <img
                src="/brand/wordmark-white.png"
                alt="liebao-bid-bot"
                className={`logo-dark w-auto object-contain transition-all duration-200 ${
                  scrolled ? "h-5" : "h-7"
                }`}
              />
            </div>
            <nav ref={navRef} className="relative flex h-full gap-6">
              {TABS.map(([id, label]) => (
                <button
                  key={id}
                  ref={(el) => {
                    tabRefs.current[id] = el ?? undefined;
                  }}
                  onClick={() => setTab(id)}
                  className={`text-sm font-medium transition-[padding,color] duration-200 ${
                    scrolled ? "py-3" : "py-4"
                  } ${tab === id ? "text-fg" : "text-fg-muted hover:text-fg"}`}
                >
                  {label}
                </button>
              ))}
              <span
                aria-hidden
                className="absolute bottom-0 h-0.5 rounded-full bg-accent transition-[left,width,opacity] duration-300 ease-out"
                style={{
                  left: indicator?.left ?? 0,
                  width: indicator?.width ?? 0,
                  opacity: indicator ? 1 : 0,
                }}
              />
            </nav>
            <div
              className={`ml-auto flex items-center gap-3 py-3 transition-[padding] duration-200 ${scrolled ? "!py-2" : ""}`}
            >
              <button
                onClick={() => setTab("setup")}
                aria-label="Setup"
                title="Setup"
                className={`group transition-colors ${tab === "setup" ? "text-accent" : "text-fg-muted hover:text-fg"}`}
              >
                <Settings size={18} className="transition-transform duration-300 group-hover:rotate-90" />
              </button>
              <ThemeToggle />
            </div>
          </div>
        </header>

        {/* Always mounted, regardless of which tab is active - generation
            keeps running in the background no matter what you're looking
            at, so the one thing telling you about it has to be visible
            the same way, not just while the Queue tab happens to be
            open. */}
        <GenerationStatusWidget />

        {/*
          Every tab stays mounted; only visibility toggles. Fetch results, in
          particular, are that page's own local state (see FetchPage) - if
          the page unmounted on tab switch, the fetched list would silently
          vanish and reappear empty on return, which is exactly the bug this
          fixes.
        */}
        <main className="mx-auto max-w-[1680px] px-8 py-6">
          <div hidden={tab !== "fetch"}>
            <FetchPage
              onQueued={(profileId) => {
                setQueueFocusProfile(profileId);
                setTab("queue");
              }}
            />
          </div>
          <div hidden={tab !== "queue"}>
            <QueuePage active={tab === "queue"} focusProfile={queueFocusProfile} />
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
