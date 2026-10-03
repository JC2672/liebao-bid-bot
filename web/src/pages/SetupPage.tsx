import { useState } from "react";
import { LayoutTemplate, SlidersHorizontal, User } from "lucide-react";
import { ProfilesPage } from "./ProfilesPage";
import { TemplatesPage } from "./TemplatesPage";
import { FieldsPage } from "./FieldsPage";

type SidebarItem = "profiles" | "templates" | "fields";

const SIDEBAR_ITEMS: [SidebarItem, string, typeof User][] = [
  ["profiles", "Profiles", User],
  ["templates", "Templates", LayoutTemplate],
  ["fields", "Fetch options", SlidersHorizontal],
];

/** Setup gathers every "configure this once, not a daily-use tab" screen
 * under one place with its own sidebar, rather than each getting its own
 * top-level tab forever - built to take more sidebar items later as this
 * app grows, not just the three it starts with. A bordered sidebar card +
 * a vertical divider gives the two halves real visual structure, rather
 * than bare nav buttons floating next to whatever sub-page happens to
 * render. Same mount-everything-keep-state pattern App.tsx already uses
 * for its own top-level tabs, just nested one level. */
export function SetupPage() {
  const [item, setItem] = useState<SidebarItem>("profiles");

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-lg font-semibold">Setup</h1>
        <p className="text-sm text-fg-muted">
          Profiles, resume templates, and fetch configuration - set up once, not a daily-use screen.
        </p>
      </div>

      <div className="flex gap-6">
        <nav className="flex h-fit w-52 shrink-0 flex-col gap-1 rounded-md border border-border bg-surface p-2">
          {SIDEBAR_ITEMS.map(([id, label, Icon]) => (
            <button
              key={id}
              onClick={() => setItem(id)}
              className={`flex items-center gap-2.5 rounded-md border-l-2 px-2.5 py-2 text-left text-sm font-medium transition-colors ${
                item === id
                  ? "border-accent bg-accent-wash text-accent"
                  : "border-transparent text-fg-muted hover:bg-surface-hover hover:text-fg"
              }`}
            >
              <Icon size={16} className="shrink-0" />
              {label}
            </button>
          ))}
        </nav>

        <div className="min-w-0 flex-1 border-l border-border pl-6">
          <div hidden={item !== "profiles"}>
            <ProfilesPage />
          </div>
          <div hidden={item !== "templates"}>
            <TemplatesPage />
          </div>
          <div hidden={item !== "fields"}>
            <FieldsPage />
          </div>
        </div>
      </div>
    </div>
  );
}
