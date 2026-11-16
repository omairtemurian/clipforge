import type { Job } from "@/api/types";

/** One event of GET /jobs/{id}/events (SPEC 7). */
export interface JobEvent {
  step: string;
  progress: number;
  status: Job["status"];
  message: string;
  /** The share of the whole job done, 0 to 1 (the server weighs the steps). */
  overall_progress?: number;
  /** The seconds the job still needs; null while unknown. */
  eta_seconds?: number | null;
}

export type StepState = "pending" | "running" | "done" | "failed";

export interface ProcessingStep {
  id: string;
  label: string;
  /** The job steps (Job.step) this line of the list stands for, in order. */
  jobSteps: readonly string[];
}

/** The steps the user sees (SPEC 8.3); Captions is the render, which burns them in. */
export const PROCESSING_STEPS: readonly ProcessingStep[] = [
  { id: "download", label: "Download", jobSteps: ["ingest"] },
  { id: "transcribe", label: "Transcribe", jobSteps: ["transcribe"] },
  {
    id: "analyze",
    label: "Analyze audio",
    jobSteps: ["signals", "visuals", "enrich"],
  },
  { id: "find", label: "Find clips", jobSteps: ["curate"] },
  { id: "score", label: "Score", jobSteps: ["score", "snap"] },
  { id: "reframe", label: "Reframe", jobSteps: ["reframe"] },
  { id: "captions", label: "Captions", jobSteps: ["render"] },
];

/**
 * The ingest progress band in which it converts the video to H.264 (backend
 * pipeline/ingest.py CONVERT_START..SOURCE_READY): the conversion reports
 * start when it begins and rises toward end.
 */
export const INGEST_CONVERT_BAND = { start: 0.51, end: 0.9 } as const;

/** A part of a step that the processing view shows under it. */
export interface SubStep {
  label: string;
  /** The share of the sub-step that is done, from 0 to 1. */
  progress: number;
}

/**
 * The sub-step a running job is in, or null: "Converting video" while the
 * ingest step converts its source (INGEST_CONVERT_BAND).
 */
export function subStep(event: JobEvent | null): SubStep | null {
  if (event?.status !== "running" || event.step !== "ingest") return null;
  const { start, end } = INGEST_CONVERT_BAND;
  // Progress is saved rounded to 0.01, so start arrives as a float near it.
  if (event.progress < start - 0.001 || event.progress >= end) return null;
  return {
    label: "Converting video",
    progress: clamp((event.progress - start) / (end - start)),
  };
}

/** The position in PROCESSING_STEPS of a Job.step, or -1 if it is none. */
export function stepIndex(jobStep: string): number {
  return PROCESSING_STEPS.findIndex((step) => step.jobSteps.includes(jobStep));
}

/**
 * The state of every step for the latest event of a job.
 *
 * Steps before the current one are done and the ones after it pending; the
 * current one is running, or failed if the job failed. A running job that has
 * not named a step yet is at its first one. No event means nothing started.
 */
export function stepStates(event: JobEvent | null): StepState[] {
  const count = PROCESSING_STEPS.length;
  if (event === null || event.status === "queued") {
    return Array<StepState>(count).fill("pending");
  }
  if (event.status === "done") return Array<StepState>(count).fill("done");

  const current = Math.max(stepIndex(event.step), 0);
  const active: StepState = event.status === "failed" ? "failed" : "running";
  return PROCESSING_STEPS.map((_, index) => {
    if (index < current) return "done";
    return index === current ? active : "pending";
  });
}

/**
 * The share of the whole job that is done, from 0 to 1: the server's
 * overall progress when the event has it, else every listed step weighs
 * the same and a step with several job steps splits its weight.
 */
export function overallProgress(event: JobEvent | null): number {
  if (event === null || event.status === "queued") return 0;
  if (event.status === "done") return 1;
  if (typeof event.overall_progress === "number") {
    return clamp(event.overall_progress);
  }

  const index = Math.max(stepIndex(event.step), 0);
  const { jobSteps } = PROCESSING_STEPS[index];
  const part = Math.max(jobSteps.indexOf(event.step), 0);
  const within = (part + clamp(event.progress)) / jobSteps.length;
  return (index + within) / PROCESSING_STEPS.length;
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/** Whole seconds as "m:ss", or "h:mm:ss" from one hour on. */
export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = String(total % 60).padStart(2, "0");
  if (hours === 0) return `${minutes}:${secs}`;
  return `${hours}:${String(minutes).padStart(2, "0")}:${secs}`;
}

/**
 * The line a log drawer shows for an event, in the user's words: the step
 * that started, the end of the job, or the error that stopped it.
 */
export function logText(event: JobEvent): string {
  switch (event.status) {
    case "queued":
      return "Waiting in the queue.";
    case "done":
      return "All steps finished.";
    case "failed":
      return event.message;
    case "running": {
      const index = stepIndex(event.step);
      return index < 0
        ? "Started working."
        : `Started: ${PROCESSING_STEPS[index].label}.`;
    }
  }
}
