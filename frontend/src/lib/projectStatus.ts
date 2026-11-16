import type { Job, Project } from "@/api/types";
import {
  PROCESSING_STEPS,
  overallProgress,
  stepIndex,
  type JobEvent,
} from "./processingSteps";
import { projectName } from "./format";

/** Whether a project is waiting for or in processing. */
export function isActive(project: Pick<Project, "status">): boolean {
  return project.status === "queued" || project.status === "running";
}

/** The number of projects that are queued or running. */
export function activeCount(projects: readonly Project[]): number {
  return projects.filter(isActive).length;
}

/** A job row as the event the processing view reads (no message). */
export function jobEvent(job: Job): JobEvent {
  return {
    step: job.step,
    progress: job.progress,
    status: job.status,
    message: "",
    overall_progress: job.overall_progress,
    eta_seconds: job.eta_seconds,
  };
}

/** The label of a project that waits in the queue (it has no progress yet). */
export const WAITING_LABEL = "Waiting in the queue";

/** What a project card shows of a queued or running project. */
export interface ProjectProgress {
  /** The current step in the user's words. */
  label: string;
  /** Whole percent of the job that is done, 0 to 100. */
  percent: number;
  /** Seconds the job still needs; null while unknown. */
  etaSeconds: number | null;
}

/**
 * The step, progress and ETA of an active project: the step from its
 * process job, the overall progress and ETA from the job once it is known
 * (it is polled as fast as the projects), else from the project row; null
 * for a project that is done or failed. Before its job is known it is
 * waiting (queued) or starting (running).
 */
export function projectProgress(
  project: Pick<Project, "status" | "overall_progress" | "eta_seconds">,
  job: Job | undefined,
): ProjectProgress | null {
  if (!isActive(project)) return null;
  const event = job === undefined ? null : jobEvent(job);
  if (event?.status === "queued" || (!event && project.status === "queued")) {
    return { label: WAITING_LABEL, percent: 0, etaSeconds: null };
  }
  if (event === null) {
    return {
      label: "Starting",
      percent: Math.round(project.overall_progress * 100),
      etaSeconds: project.eta_seconds,
    };
  }
  const index = stepIndex(event.step);
  const label = index < 0 ? "Starting" : PROCESSING_STEPS[index].label;
  return {
    label,
    percent: Math.round(overallProgress(event) * 100),
    etaSeconds: event.eta_seconds ?? null,
  };
}

/** Whether a finished project shows the "New" badge: not opened yet. */
export function isNew(project: Pick<Project, "status" | "opened_at">): boolean {
  return project.status === "done" && project.opened_at === null;
}

/** The projects whose name contains query (any case); all for "". */
export function matchProjects(projects: Project[], query: string): Project[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return projects;
  return projects.filter((project) =>
    projectName(project).toLowerCase().includes(needle),
  );
}

/** The status filters of the Projects page. */
export type ProjectFilter =
  "all" | "processing" | "ready" | "failed" | "archived";

export const PROJECT_FILTERS: { value: ProjectFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "processing", label: "Processing" },
  { value: "ready", label: "Ready" },
  { value: "failed", label: "Failed" },
  { value: "archived", label: "Archived" },
];

/** Whether the storage manager archived a project. */
export function isArchived(project: Pick<Project, "archived_at">): boolean {
  return project.archived_at !== null && project.archived_at !== undefined;
}

/** The projects a status filter keeps: queued or running ones, ready ones
 * (done, not archived), failed ones, archived ones, or all. */
export function filterProjects(
  projects: Project[],
  filter: ProjectFilter,
): Project[] {
  switch (filter) {
    case "processing":
      return projects.filter(isActive);
    case "ready":
      return projects.filter((p) => p.status === "done" && !isArchived(p));
    case "failed":
      return projects.filter((p) => p.status === "failed" && !isArchived(p));
    case "archived":
      return projects.filter(isArchived);
    default:
      return projects;
  }
}
