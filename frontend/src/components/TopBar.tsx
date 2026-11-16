import { MagnifyingGlassIcon } from "@phosphor-icons/react";
import { Fragment, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useProject } from "@/api/projects";
import { NotificationBell } from "@/components/notifications/NotificationBell";
import { projectName } from "@/lib/format";
import { crumbLabel, LIBRARY_PATH, PROJECTS_PATH } from "./navigation";

/** The title of the project a crumb names; its id until it loads. */
function ProjectCrumb({ id, segment }: { id: number; segment: string }) {
  const project = useProject(id);
  return <>{project.data ? projectName(project.data) : segment}</>;
}

/** The label of one crumb: a project's title after "projects". */
function CrumbLabel({ path, segment }: { path: string; segment: string }) {
  const id = Number(segment);
  if (path === `${PROJECTS_PATH}/${segment}` && Number.isInteger(id)) {
    return <ProjectCrumb id={id} segment={segment} />;
  }
  return <>{crumbLabel(segment)}</>;
}

/** Breadcrumb of the current path: "Projects / <project title>". */
function Breadcrumb({ pathname }: { pathname: string }) {
  const segments = pathname.split("/").filter(Boolean);
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex min-w-0 items-center gap-1.5 text-sm"
    >
      {segments.map((segment, index) => {
        const path = `/${segments.slice(0, index + 1).join("/")}`;
        const last = index === segments.length - 1;
        return (
          <Fragment key={path}>
            {index > 0 && <span className="text-muted-foreground">/</span>}
            {last ? (
              <span aria-current="page" className="truncate font-medium">
                <CrumbLabel path={path} segment={segment} />
              </span>
            ) : (
              <Link
                to={path}
                className="shrink-0 rounded text-muted-foreground transition-colors outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <CrumbLabel path={path} segment={segment} />
              </Link>
            )}
          </Fragment>
        );
      })}
    </nav>
  );
}

/** Top bar of the inner pages: breadcrumb, a search field (cmd+K) that
 * searches the transcripts in the Library, and the notifications bell. */
export function TopBar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    function focusOnShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", focusOnShortcut);
    return () => window.removeEventListener("keydown", focusOnShortcut);
  }, []);

  function search(event: React.FormEvent) {
    event.preventDefault();
    const text = query.trim();
    navigate(text ? `/library?q=${encodeURIComponent(text)}` : LIBRARY_PATH);
  }

  return (
    <header className="grid h-14 shrink-0 grid-cols-[1fr_minmax(0,28rem)_1fr] items-center gap-4 bg-background px-page">
      <Breadcrumb pathname={pathname} />
      <form role="search" onSubmit={search} className="relative">
        <MagnifyingGlassIcon className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <input
          ref={inputRef}
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search keywords or moments…"
          aria-label="Search keywords or moments"
          className="h-9 w-full rounded-full border border-input bg-field pr-12 pl-9 text-body transition-colors outline-none placeholder:text-muted-foreground hover:border-foreground/25 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        />
        <kbd className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 rounded-md bg-muted px-1.5 text-[10px] text-muted-foreground">
          ⌘K
        </kbd>
      </form>
      <NotificationBell />
    </header>
  );
}
