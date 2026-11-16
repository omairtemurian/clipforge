import type { ReactNode } from "react";
import {
  FolderOpenIcon,
  MagnifyingGlassMinusIcon,
} from "@phosphor-icons/react";
import { useProjects } from "@/api/projects";
import type { Project } from "@/api/types";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ProjectCard, ProjectCardSkeleton } from "@/components/ProjectCard";

const SKELETONS = 4;

const GRID =
  "grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-x-6 gap-y-8";

interface ProjectGridProps {
  /** Which of the projects (newest first) to show; all by default. */
  pick?: (projects: Project[]) => Project[];
  /** Shown when there are projects but `pick` keeps none. */
  noMatch?: ReactNode;
}

/**
 * A grid of project cards, newest first, with loading skeletons, an empty
 * state and a retry when the projects cannot load.
 */
export function ProjectGrid({ pick, noMatch }: ProjectGridProps) {
  const projects = useProjects();

  if (projects.isPending) {
    return (
      <div className={GRID}>
        {Array.from({ length: SKELETONS }, (_, index) => (
          <ProjectCardSkeleton key={index} />
        ))}
      </div>
    );
  }
  if (projects.isError) {
    return (
      <div className="flex flex-col items-center gap-4 py-12 text-body text-muted-foreground">
        <p>Could not load your projects.</p>
        <Button variant="outline" onClick={() => void projects.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  if (projects.data.length === 0) {
    return (
      <EmptyState icon={FolderOpenIcon} title="No projects yet">
        Paste a video link or drop a file on Home. Your projects show up here.
      </EmptyState>
    );
  }
  const shown = pick ? pick(projects.data) : projects.data;
  if (shown.length === 0) {
    return (
      <EmptyState icon={MagnifyingGlassMinusIcon} title="Nothing found">
        {noMatch}
      </EmptyState>
    );
  }
  return (
    <div className={GRID}>
      {shown.map((project) => (
        <ProjectCard key={project.id} project={project} />
      ))}
    </div>
  );
}
