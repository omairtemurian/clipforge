import { useState } from "react";
import { FilmStripIcon } from "@phosphor-icons/react";
import { Link } from "react-router-dom";
import { apiUrl } from "@/api/client";
import { useClipCount } from "@/api/clips";
import { useProcessJob } from "@/api/jobs";
import type { Project } from "@/api/types";
import { projectPath } from "@/components/navigation";
import { ProjectMenu } from "@/components/ProjectMenu";
import { ProgressPill } from "@/components/ProgressPill";
import { Pill, type PillTone } from "@/components/ui/pill";
import { Skeleton } from "@/components/ui/skeleton";
import { clipCountLabel, formatDate, projectName } from "@/lib/format";
import { MEDIA_FRAME } from "@/lib/surfaces";
import {
  WAITING_LABEL,
  isActive,
  isArchived,
  isNew,
  projectProgress,
} from "@/lib/projectStatus";
import type { ProjectProgress } from "@/lib/projectStatus";

const STATUS: Record<Project["status"], { label: string; tone: PillTone }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Processing", tone: "primary" },
  done: { label: "Ready", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
};

/** A small pill with the status of a project. */
export function StatusPill({ status }: { status: Project["status"] }) {
  const { label, tone } = STATUS[status];
  return <Pill tone={tone}>{label}</Pill>;
}

function Thumbnail({
  project,
  name,
  progress,
}: {
  project: Project;
  name: string;
  progress: ProjectProgress | null;
}) {
  const [broken, setBroken] = useState(false);
  const showImage = project.thumbnail_path !== "" && !broken;

  return (
    <div className={`${MEDIA_FRAME} aspect-video`}>
      {showImage ? (
        <img
          src={apiUrl(`/media/${project.id}/thumbnail`)}
          alt=""
          loading="lazy"
          onError={() => setBroken(true)}
          className="size-full object-cover transition-transform duration-200 group-hover:scale-[1.02]"
        />
      ) : (
        <div className="flex size-full items-center justify-center text-muted-foreground">
          <FilmStripIcon className="size-8" aria-hidden />
        </div>
      )}
      {progress && progress.label !== WAITING_LABEL && (
        <ProgressPill name={name} progress={progress} />
      )}
      <div className="absolute bottom-2 left-2 flex gap-1">
        <span className="rounded-full bg-overlay backdrop-blur-sm">
          <StatusPill status={project.status} />
        </span>
        {isArchived(project) && <Pill tone="overlay">Archived</Pill>}
      </div>
      {isNew(project) && (
        <span
          data-testid="new-badge"
          className="absolute top-2 right-11 rounded-full bg-primary px-2 py-0.5 text-caption font-medium text-primary-foreground"
        >
          New
        </span>
      )}
    </div>
  );
}

/**
 * A project of a projects grid: thumbnail with its status, title, clips and
 * date; while it is queued or running a progress pill (percent and ETA) on
 * the thumbnail and the current step (its process job polled every 2 s); a
 * "New" badge once it is done until it is opened. The card opens the project
 * (the processing view until it is done); the kebab renames or deletes it.
 */
export function ProjectCard({ project }: { project: Project }) {
  const clips = useClipCount(project);
  const active = isActive(project);
  const job = useProcessJob(project.id, { poll: active, enabled: active });
  const progress = projectProgress(project, job.data);
  const name = projectName(project);
  const details = [
    clips.data === undefined ? null : clipCountLabel(clips.data),
    formatDate(project.created_at),
  ].filter(Boolean);

  return (
    <article aria-label={name} className="group relative min-w-0">
      <Link
        to={projectPath(project.id)}
        aria-label={`Open ${name}`}
        className="block rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-4 focus-visible:ring-offset-background"
      >
        <Thumbnail project={project} name={name} progress={progress} />
        <h3
          className="mt-3 truncate text-body font-medium transition-colors group-hover:text-primary-ink"
          title={name}
        >
          {name}
        </h3>
        <p className="mt-1 text-caption text-muted-foreground">
          {details.join(" · ")}
        </p>
        {progress && (
          <p className="mt-1 truncate text-caption text-primary-ink">
            {progress.label}
          </p>
        )}
      </Link>
      <div className="absolute top-2 right-2">
        <ProjectMenu project={project} />
      </div>
    </article>
  );
}

/** The grey placeholder shown while the projects load. */
export function ProjectCardSkeleton() {
  return (
    <div aria-hidden data-testid="project-skeleton">
      <Skeleton className="aspect-video rounded-xl" />
      <Skeleton className="mt-3 h-4 w-3/4" />
      <Skeleton className="mt-2 h-3 w-1/3" />
    </div>
  );
}
