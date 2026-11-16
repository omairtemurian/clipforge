import {
  MoonIcon,
  QuestionIcon,
  SidebarSimpleIcon,
  SunIcon,
} from "@phosphor-icons/react";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";
import { Link, NavLink } from "react-router-dom";
import { useActiveProjectCount } from "@/api/projects";
import { LogoMark } from "@/components/LogoMark";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";
import {
  CREATE_NAV,
  HELP_URL,
  PROJECTS_PATH,
  PUBLISH_NAV,
  SETTINGS_NAV,
  type NavItem,
} from "./navigation";

const LINK_CLASS =
  "flex h-9 items-center gap-2 rounded-xl px-1 text-body font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50";

const GROUP_LABEL = "px-3 pb-2 text-caption font-medium text-muted-foreground";

/**
 * A nav icon in its rounded-square tile: the active link's icon is filled
 * in ember on a soft grey tile, the others are regular weight.
 */
function NavIcon({
  icon: Icon,
  active = false,
}: {
  icon: PhosphorIcon;
  active?: boolean;
}) {
  return (
    <span
      aria-hidden
      className={cn(
        "flex size-8 shrink-0 items-center justify-center rounded-[0.625rem] transition-colors",
        active && "bg-sidebar-accent text-primary",
      )}
    >
      <Icon weight={active ? "fill" : "regular"} className="size-5" />
    </span>
  );
}

/** The number on a link (projects in progress); hidden at 0. */
function Badge({ count, collapsed }: { count: number; collapsed: boolean }) {
  if (count === 0) return null;
  return (
    <span
      aria-hidden
      data-testid="nav-badge"
      className={cn(
        "flex h-4.5 min-w-4.5 items-center justify-center rounded-full bg-primary px-1 text-[0.65rem] leading-none font-semibold text-primary-foreground",
        collapsed ? "absolute -top-1 right-1.5" : "ml-auto",
      )}
    >
      {count}
    </span>
  );
}

function SidebarLink({
  item,
  collapsed,
  badge = 0,
}: {
  item: NavItem;
  collapsed: boolean;
  badge?: number;
}) {
  const label = badge > 0 ? `${item.label}, ${badge} in progress` : item.label;
  return (
    <NavLink
      to={item.path}
      end={item.path === "/"}
      title={collapsed ? label : undefined}
      aria-label={label}
      className={({ isActive }) =>
        cn(
          LINK_CLASS,
          collapsed && "relative justify-center px-0",
          isActive
            ? "font-semibold text-sidebar-accent-foreground"
            : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
        )
      }
    >
      {({ isActive }) => (
        <>
          <NavIcon icon={item.icon} active={isActive} />
          {!collapsed && <span>{item.label}</span>}
          <Badge count={badge} collapsed={collapsed} />
        </>
      )}
    </NavLink>
  );
}

/** The sun/moon switch between the light and the dark theme. */
function ThemeToggle({ collapsed }: { collapsed: boolean }) {
  const { theme, setChoice } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  const label = next === "dark" ? "Dark theme" : "Light theme";
  return (
    <button
      type="button"
      aria-label={`Switch to ${next} theme`}
      title={collapsed ? label : undefined}
      onClick={() => setChoice(next)}
      className={cn(
        LINK_CLASS,
        "w-full cursor-pointer text-muted-foreground hover:bg-muted/60 hover:text-foreground",
        collapsed && "justify-center px-0",
      )}
    >
      <NavIcon icon={next === "dark" ? MoonIcon : SunIcon} />
      {!collapsed && <span>{label}</span>}
    </button>
  );
}

interface SidebarProps {
  collapsed: boolean;
  onToggle: () => void;
}

/**
 * Left navigation: text logo, the main links (Projects with the number of
 * queued or running projects), then Settings and Help.
 */
export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const active = useActiveProjectCount();
  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-3 py-4 transition-[width] duration-200",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <div
        className={cn(
          "mb-8 flex items-center",
          collapsed ? "flex-col gap-3" : "justify-between px-1",
        )}
      >
        <Link
          to="/"
          aria-label="ClipForge home"
          className="flex items-center gap-2.5 rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <LogoMark />
          {!collapsed && (
            <span className="text-lg font-semibold tracking-tight">
              Clip<span className="text-primary-ink">Forge</span>
            </span>
          )}
        </Link>
        <button
          type="button"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="rounded-lg p-1.5 text-muted-foreground transition-colors outline-none hover:bg-muted/60 hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
          onClick={onToggle}
        >
          <SidebarSimpleIcon className="size-4" />
        </button>
      </div>

      <nav aria-label="Main navigation" className="space-y-1">
        {!collapsed && <p className={GROUP_LABEL}>Create</p>}
        {CREATE_NAV.map((item) => (
          <SidebarLink
            key={item.path}
            item={item}
            collapsed={collapsed}
            badge={item.path === PROJECTS_PATH ? (active.data ?? 0) : 0}
          />
        ))}
      </nav>

      <nav aria-label="Post navigation" className="mt-8 space-y-1">
        {!collapsed && <p className={GROUP_LABEL}>Post</p>}
        {PUBLISH_NAV.map((item) => (
          <SidebarLink key={item.path} item={item} collapsed={collapsed} />
        ))}
      </nav>

      <div className="mt-auto space-y-1">
        <SidebarLink item={SETTINGS_NAV} collapsed={collapsed} />
        <a
          href={HELP_URL}
          target="_blank"
          rel="noreferrer"
          aria-label="Help"
          title={collapsed ? "Help" : undefined}
          className={cn(
            LINK_CLASS,
            collapsed && "justify-center px-0",
            "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
          )}
        >
          <NavIcon icon={QuestionIcon} />
          {!collapsed && <span>Help</span>}
        </a>
        <ThemeToggle collapsed={collapsed} />
      </div>
    </aside>
  );
}
