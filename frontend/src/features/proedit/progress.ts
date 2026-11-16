import type { ProEditRun } from "@/api/types";
import type { JobEvent, StepState } from "@/lib/processingSteps";

export interface ProgressStep {
  key: "plan" | "proxy" | "critic" | "final";
  label: string;
  state: StepState;
}

const ORDER = ["plan", "proxy", "critic", "final"] as const;

/** Whether a run of mode with options has the critic steps (SPEC-v3 3.8). */
function hasCritic(run: Pick<ProEditRun, "mode" | "options">): boolean {
  if (run.mode === "critic") return true;
  if (run.mode === "render") return false;
  return run.options?.use_critic ?? true;
}

/** The steps a run goes through: plan, proxy, critic, final; a render run
 * is the final step alone, a critic run has no plan step. */
export function runSteps(
  run: Pick<ProEditRun, "mode" | "options">,
): ProgressStep["key"][] {
  if (run.mode === "render") return ["final"];
  const critic = hasCritic(run);
  return ORDER.filter(
    (key) =>
      (key !== "plan" || run.mode !== "critic") &&
      (critic || (key !== "proxy" && key !== "critic")),
  );
}

/** The critic round a job is in: during "critic" its progress is
 * (n - 1) / total, so round n of total (capped at total). */
export function criticRound(progress: number, total: number): number {
  return Math.min(total, Math.floor(progress * total + 1e-9) + 1);
}

/** The label of a step: "Critic round 2/3" while the critic works. */
function stepLabel(
  key: ProgressStep["key"],
  event: JobEvent | null,
  rounds: number,
): string {
  switch (key) {
    case "plan":
      return "Plan";
    case "proxy":
      return "Proxy";
    case "critic": {
      const n =
        event?.step === "critic" ? criticRound(event.progress, rounds) : 1;
      return `Critic round ${n}/${rounds}`;
    }
    case "final":
      return "Final render";
  }
}

/**
 * The steps of a run as the progress view shows them, from the run and
 * the latest event of its job: the steps before the job's step are done,
 * its step runs (or failed with the job), the rest wait; all are done
 * once the job is done.
 * rounds is the critic's round cap (GET /proedit/status).
 */
export function progressSteps(
  run: Pick<ProEditRun, "mode" | "options">,
  event: JobEvent | null,
  rounds: number,
): ProgressStep[] {
  const keys = runSteps(run);
  const current =
    event === null ? 0 : keys.indexOf(event.step as ProgressStep["key"]);
  const active = Math.max(current, 0);
  const done = event?.status === "done";
  const failed = event?.status === "failed";
  return keys.map((key, index) => ({
    key,
    label: stepLabel(key, event, rounds),
    state:
      done || index < active
        ? "done"
        : index > active
          ? "pending"
          : failed
            ? "failed"
            : "running",
  }));
}

/** The whole percent of a job that is done, from its latest event. */
export function overallPercent(event: JobEvent | null): number {
  if (event === null) return 0;
  if (event.status === "done") return 100;
  return Math.round((event.overall_progress ?? 0) * 100);
}
