import { useQueryClient } from "@tanstack/react-query";
import { ClockIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { useProcessJob } from "@/api/jobs";
import { projectsKey } from "@/api/projects";
import type { Project } from "@/api/types";
import { StatusPill } from "@/components/ProjectCard";
import { LogDrawer } from "@/components/processing/LogDrawer";
import { StepList } from "@/components/processing/StepList";
import { useElapsed } from "@/hooks/useElapsed";
import { useJobEvents } from "@/hooks/useJobEvents";
import { formatDate, parseApiDate, projectName } from "@/lib/format";
import { formatEta } from "@/lib/projectEta";
import {
  formatElapsed,
  overallProgress,
  stepStates,
} from "@/lib/processingSteps";
import { cardClass } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

/**
 * The view of a project that is not done: its steps, overall progress, the
 * time since it was added and a live log. The events start with the job's
 * current state, so coming back to the page shows where it is.
 */
export function Processing({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const job = useProcessJob(project.id);
  const { event, log } = useJobEvents(job.data?.id, () => {
    void queryClient.invalidateQueries({
      queryKey: [...projectsKey, project.id],
    });
  });

  const status = event?.status ?? project.status;
  const active = status === "queued" || status === "running";
  const elapsed = useElapsed(
    parseApiDate(project.created_at).getTime(),
    active,
  );
  // A job already over when the page opened has no known duration.
  const showElapsed = active || log.length > 1;
  const states = stepStates(event);
  const percent = Math.round(overallProgress(event) * 100);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-5 px-page pt-section pb-6">
      <header>
        <div className="flex items-center gap-3">
          <h1 className="truncate text-title">{projectName(project)}</h1>
          <StatusPill status={status} />
        </div>
        <p className="mt-2 text-body text-muted-foreground">
          Added {formatDate(project.created_at)}.{" "}
          {status === "failed"
            ? "Processing stopped."
            : "You can leave this page; ClipForge keeps working."}
        </p>
      </header>

      <section className={cn(cardClass(), "p-6")}>
        <div className="mb-2 flex items-center justify-between text-body">
          <span className="font-medium">Overall progress</span>
          <span className="flex items-center gap-3 text-muted-foreground">
            {showElapsed && (
              <span
                className="flex items-center gap-1"
                aria-label="Elapsed time"
              >
                <ClockIcon className="size-3.5" aria-hidden />
                {formatElapsed(elapsed)}
              </span>
            )}
            <span>
              {percent}%{active && ` · ${formatEta(event?.eta_seconds)}`}
            </span>
          </span>
        </div>
        <div
          role="progressbar"
          aria-label="Overall progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          className="h-2.5 overflow-hidden rounded-full bg-muted"
        >
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-500"
            style={{ width: `${percent}%` }}
          />
        </div>
        <div className="mt-4 border-t border-border pt-4">
          <StepList states={states} event={event} />
        </div>
      </section>

      {status === "failed" && (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-2xl border border-destructive/40 bg-destructive/10 p-4 text-body text-destructive"
        >
          <WarningCircleIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
          <span>{event?.message || job.data?.error || "The job failed."}</span>
        </div>
      )}

      <LogDrawer lines={log} />
    </div>
  );
}
