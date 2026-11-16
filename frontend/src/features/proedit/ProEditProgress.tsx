import { ArrowSquareOutIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { projectsKey } from "@/api/projects";
import type { ProEditStarted } from "@/api/types";
import { StepIcon } from "@/components/processing/StepList";
import { Button } from "@/components/ui/button";
import { useJobEvents } from "@/hooks/useJobEvents";
import { formatEta } from "@/lib/projectEta";
import { cn } from "@/lib/utils";
import { proEditPath } from "./paths";
import { overallPercent, progressSteps } from "./progress";
import { RunNotes } from "./RunNotes";
import { useProEditRuns, useProEditStatus } from "./runApi";

const DEFAULT_ROUNDS = 2;

interface ProEditProgressProps {
  /** The queued run: its variant, run and job. */
  started: ProEditStarted;
  /** The clip the variant was made from (its Pro Edit page). */
  originalId: number;
}

/**
 * The progress of a Pro Edit run (SPEC-v3 3.8): plan → proxy → critic
 * round n/N → final render from its job's events, the overall bar with the
 * shared ETA, the error when it failed, what post-processing moved or
 * dropped once it is done (RunNotes), and the way to the variants. The clip
 * lists are loaded again when the job ends.
 */
export function ProEditProgress({ started, originalId }: ProEditProgressProps) {
  const queryClient = useQueryClient();
  const status = useProEditStatus();
  const rounds = status.data?.critic_max_rounds ?? DEFAULT_ROUNDS;
  const { event } = useJobEvents(started.job_id, () => {
    void queryClient.invalidateQueries({
      queryKey: [...projectsKey, started.clip.project_id],
    });
    void queryClient.invalidateQueries({ queryKey: ["proedit", "variants"] });
    void queryClient.invalidateQueries({
      queryKey: ["clips", started.clip.id],
    });
  });
  const steps = progressSteps(started.run, event, rounds);
  const percent = overallPercent(event);
  const ended = event?.status === "done" || event?.status === "failed";
  const runs = useProEditRuns(started.clip.id, event?.status === "done");
  const run = runs.data?.find((r) => r.id === started.run.id);

  return (
    <div className="mt-5 flex flex-col gap-4">
      <div>
        <div className="mb-2 flex items-center justify-between text-body">
          <span className="truncate font-medium">{started.clip.title}</span>
          <span className="shrink-0 text-muted-foreground tabular-nums">
            {percent}%{!ended && ` · ${formatEta(event?.eta_seconds)}`}
          </span>
        </div>
        <div
          role="progressbar"
          aria-label="Pro Edit progress"
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
      </div>
      <ol aria-label="Pro Edit steps" className="flex flex-col gap-1.5">
        {steps.map((step) => (
          <li
            key={step.key}
            data-state={step.state}
            className={cn(
              "flex items-center gap-3 rounded-xl px-3 py-2",
              step.state === "running" && "bg-muted/60 ring-1 ring-primary/30",
            )}
          >
            <StepIcon state={step.state} />
            <span
              className={cn(
                "text-body",
                step.state === "pending"
                  ? "text-muted-foreground"
                  : "font-medium text-foreground",
              )}
            >
              {step.label}
            </span>
          </li>
        ))}
      </ol>
      {event?.status === "failed" && (
        <p
          role="alert"
          className="flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/10 p-3 text-body text-destructive"
        >
          <WarningCircleIcon className="mt-0.5 size-4 shrink-0" aria-hidden />
          {event.message || "The Pro Edit failed."}
        </p>
      )}
      {event?.status === "done" && (
        <p className="text-body text-success">
          The Pro Edit variant is ready. The original clip is unchanged.
        </p>
      )}
      {event?.status === "done" && run && <RunNotes notes={run.notes} />}
      <div className="flex justify-end">
        <Button variant="outline" asChild>
          <Link to={proEditPath(originalId, started.clip.id)}>
            <ArrowSquareOutIcon aria-hidden />
            Open Pro Edit variants
          </Link>
        </Button>
      </div>
    </div>
  );
}
