import { NavLink } from "react-router-dom";
import {
  AGENTS_SETTINGS_NAV,
  SETTINGS_NAV,
  STORAGE_SETTINGS_NAV,
} from "@/components/navigation";
import { cn } from "@/lib/utils";

const TABS = [
  { ...SETTINGS_NAV, label: "General" },
  AGENTS_SETTINGS_NAV,
  STORAGE_SETTINGS_NAV,
];

/** The tabs of the settings pages: General, AI agents & API and Storage. */
export function SettingsTabs() {
  return (
    <nav
      aria-label="Settings pages"
      className="flex gap-1 border-b border-border"
    >
      {TABS.map(({ label, path, icon: Icon }) => (
        <NavLink
          key={path}
          to={path}
          end
          className={({ isActive }) =>
            cn(
              "-mb-px flex items-center gap-2 border-b-2 px-3 py-2 text-body transition-colors",
              isActive
                ? "border-primary font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )
          }
        >
          <Icon aria-hidden className="size-4" />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
