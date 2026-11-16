import { CaretRightIcon } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import type { Project } from "@/api/types";
import { ProjectGrid } from "@/components/ProjectGrid";

const RECENT = 8;

function recent(projects: Project[]): Project[] {
  return projects.slice(0, RECENT);
}

/** The "Recent projects" grid of Home, with a link to all projects. */
export function RecentProjects() {
  return (
    <section aria-labelledby="recent-projects" className="mt-20">
      <div className="mb-6 flex items-center gap-4">
        <h2 id="recent-projects" className="text-section text-muted-foreground">
          Recent projects
        </h2>
        <Link
          to="/projects"
          className="inline-flex items-center gap-0.5 rounded-md text-body font-medium transition-colors outline-none hover:text-primary-ink focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          View all
          <CaretRightIcon className="size-4" aria-hidden />
        </Link>
      </div>
      <ProjectGrid pick={recent} />
    </section>
  );
}
