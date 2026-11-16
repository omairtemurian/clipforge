import {
  CheckIcon,
  CircleIcon,
  CircleNotchIcon,
  XIcon,
} from "@phosphor-icons/react";
import {
  PROCESSING_STEPS,
  subStep,
  type JobEvent,
  type StepState,
} from "@/lib/processingSteps";
import { Pill, type PillTone } from "@/components/ui/pill";
import { cn } from "@/lib/utils";

const STATE_TONE: Record<StepState, PillTone> = {
  pending: "neutral",
  running: "primary",
  done: "success",
  failed: "danger",
};

const STATE_TEXT: Record<StepState, string> = {
  pending: "Waiting",
  running: "In progress",
  done: "Done",
  failed: "Failed",
};

/** The round icon of a step's state (done, running, failed, waiting). */
export function StepIcon({ state }: { state: StepState }) {
  const base = "flex size-7 shrink-0 items-center justify-center rounded-full";
  switch (state) {
    case "done":
      return (
        <span className={cn(base, "bg-success/15 text-success")}>
          <CheckIcon className="size-4" aria-hidden />
        </span>
      );
    case "running":
      return (
        <span className={cn(base, "bg-primary/20 text-primary-ink")}>
          <CircleNotchIcon className="size-4 animate-spin" aria-hidden />
        </span>
      );
    case "failed":
      return (
        <span className={cn(base, "bg-destructive/20 text-destructive")}>
          <XIcon className="size-4" aria-hidden />
        </span>
      );
    case "pending":
      return (
        <span
          className={cn(base, "border border-border text-muted-foreground")}
        >
          <CircleIcon className="size-4" aria-hidden />
        </span>
      );
  }
}

/**
 * The processing steps in order, each with an icon for its state; a running
 * step shows its current sub-step (such as "Converting video") below it.
 */
export function StepList({
  states,
  event,
}: {
  states: StepState[];
  event: JobEvent | null;
}) {
  const sub = subStep(event);
  return (
    <ol className="flex flex-col gap-1.5" aria-label="Processing steps">
      {PROCESSING_STEPS.map((step, index) => {
        const state = states[index];
        const percent =
          state === "running" && event
            ? ` ${Math.round(event.progress * 100)}%`
            : "";
        const stepSub =
          state === "running" && event && step.jobSteps.includes(event.step)
            ? sub
            : null;
        return (
          <li
            key={step.id}
            data-state={state}
            className={cn(
              "flex items-center gap-3 rounded-xl px-3 py-2.5",
              state === "running" && "bg-muted/60 ring-1 ring-primary/30",
            )}
          >
            <StepIcon state={state} />
            <span className="flex flex-1 flex-col">
              <span
                className={cn(
                  "text-body",
                  state === "pending"
                    ? "text-muted-foreground"
                    : "font-medium text-foreground",
                )}
              >
                {step.label}
              </span>
              {stepSub && (
                <span
                  className="text-caption text-muted-foreground"
                  aria-label="Current sub-step"
                >
                  {stepSub.label} {Math.round(stepSub.progress * 100)}%
                </span>
              )}
            </span>
            <Pill tone={STATE_TONE[state]}>
              {STATE_TEXT[state]}
              {percent}
            </Pill>
          </li>
        );
      })}
    </ol>
  );
}
