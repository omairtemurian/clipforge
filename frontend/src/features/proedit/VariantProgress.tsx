import type { Clip } from "@/api/types";
import { ProgressPill } from "@/components/ProgressPill";
import { useJobEvents } from "@/hooks/useJobEvents";
import { overallPercent } from "./progress";
import { useProEditRuns } from "./runApi";

/** The progress pill over a variant's preview while its Pro Edit job is
 * queued or running (the newest run's job events). */
function RunProgress({ clip }: { clip: Clip }) {
  const runs = useProEditRuns(clip.id);
  const run = runs.data?.[0];
  const active = run && (run.status === "queued" || run.status === "running");
  const { event } = useJobEvents(
    active ? (run.job_id ?? undefined) : undefined,
  );
  if (!active) return null;
  return (
    <ProgressPill
      name={clip.title}
      progress={{
        label: "Pro Edit",
        percent: overallPercent(event),
        etaSeconds: event?.eta_seconds ?? null,
      }}
    />
  );
}

/** The Pro Edit progress over a variant's card while it is rendering;
 * nothing for an original or a variant at rest. */
export function VariantProgress({ clip }: { clip: Clip }) {
  if (clip.variant !== "pro_edit" || clip.status !== "rendering") return null;
  return <RunProgress clip={clip} />;
}
