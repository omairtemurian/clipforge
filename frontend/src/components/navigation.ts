import {
  BroadcastIcon,
  CalendarDotsIcon,
  ClockCounterClockwiseIcon,
  FolderOpenIcon,
  FoldersIcon,
  GearIcon,
  HardDrivesIcon,
  HouseIcon,
  MagnifyingGlassIcon,
  MegaphoneIcon,
  PaletteIcon,
  PaperPlaneTiltIcon,
  RobotIcon,
  ShareNetworkIcon,
  TrayIcon,
} from "@phosphor-icons/react";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";

export interface NavItem {
  label: string;
  path: string;
  icon: PhosphorIcon;
}

export const PROJECTS_PATH = "/projects";
export const WATCHLIST_PATH = "/watchlist";
export const LIBRARY_PATH = "/library";
export const COLLECTIONS_PATH = "/collections";

export const CREATE_NAV: NavItem[] = [
  { label: "Home", path: "/", icon: HouseIcon },
  { label: "Projects", path: PROJECTS_PATH, icon: FolderOpenIcon },
  { label: "Media library", path: LIBRARY_PATH, icon: MagnifyingGlassIcon },
  { label: "Collections", path: COLLECTIONS_PATH, icon: FoldersIcon },
  { label: "Brand templates", path: "/brand-templates", icon: PaletteIcon },
  { label: "Watchlist", path: WATCHLIST_PATH, icon: BroadcastIcon },
  { label: "Campaigns", path: "/campaigns", icon: MegaphoneIcon },
];

export const INBOX_PATH = "/inbox";
export const SUBMIT_PATH = "/submit";
export const CALENDAR_PATH = "/calendar";
export const POST_HISTORY_PATH = "/post-history";

/** The "Post" group of the sidebar. */
export const PUBLISH_NAV: NavItem[] = [
  { label: "Approval inbox", path: INBOX_PATH, icon: TrayIcon },
  { label: "Ready to submit", path: SUBMIT_PATH, icon: PaperPlaneTiltIcon },
  { label: "Calendar", path: CALENDAR_PATH, icon: CalendarDotsIcon },
  {
    label: "Post history",
    path: POST_HISTORY_PATH,
    icon: ClockCounterClockwiseIcon,
  },
  { label: "Social accounts", path: "/accounts", icon: ShareNetworkIcon },
];

export const SETTINGS_NAV: NavItem = {
  label: "Settings",
  path: "/settings",
  icon: GearIcon,
};

/** Settings -> AI agents & API (API keys, MCP configs, webhooks). */
export const AGENTS_SETTINGS_NAV: NavItem = {
  label: "AI agents & API",
  path: "/settings/agents",
  icon: RobotIcon,
};

/** Settings -> Storage (disk use, cleanup, archive). */
export const STORAGE_SETTINGS_NAV: NavItem = {
  label: "Storage",
  path: "/settings/storage",
  icon: HardDrivesIcon,
};

/** The page of one project. */
export function projectPath(id: number): string {
  return `/projects/${id}`;
}

export const HELP_URL = "https://github.com/omairtemurian/clipforge#readme";

/** Label of a path segment in the breadcrumb ("projects" -> "Projects"). */
export function crumbLabel(segment: string): string {
  const known = [
    ...CREATE_NAV,
    ...PUBLISH_NAV,
    SETTINGS_NAV,
    AGENTS_SETTINGS_NAV,
    STORAGE_SETTINGS_NAV,
  ].find(({ path }) => path.split("/").at(-1) === segment);
  return known?.label ?? decodeURIComponent(segment);
}
