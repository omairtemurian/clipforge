import {
  ArrowCounterClockwiseIcon,
  MagicWandIcon,
  SealCheckIcon,
} from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { useResetPlan } from "./planApi";
import { useProEditStatus, useQueueRun } from "./runApi";

/**
 * "Regenerate with Director", "Run critic again" and "Reset to plan v1"
 * (SPEC-v3 3.8) for variant variantId. The first two queue a job that ends
 * with a render; reset stores a copy of v1 as the next version and waits for
 * Render. All are off while a job runs; the critic is off when its rounds
 * are set to 0. A refused request is shown under the buttons.
 */
export function PlanActions({
  variantId,
  version,
  busy,
}: {
  variantId: number;
  /** The current plan's version: v1 has nothing to reset to. */
  version: number;
  busy: boolean;
}) {
  const status = useProEditStatus();
  const regenerate = useQueueRun(variantId, "regenerate");
  const critic = useQueueRun(variantId, "critic");
  const reset = useResetPlan(variantId);
  const error = regenerate.error ?? critic.error ?? reset.error;
  const criticOff = status.data?.critic_max_rounds === 0;

  return (
    <section aria-label="Plan actions" className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="outline"
          disabled={busy || regenerate.isPending}
          onClick={() => regenerate.mutate()}
        >
          <MagicWandIcon aria-hidden />
          Regenerate with Director
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={busy || critic.isPending || criticOff}
          title={criticOff ? "The critic's rounds are set to 0" : undefined}
          onClick={() => critic.mutate()}
        >
          <SealCheckIcon aria-hidden />
          Run critic again
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={busy || reset.isPending || version === 1}
          onClick={() => reset.mutate()}
        >
          <ArrowCounterClockwiseIcon aria-hidden />
          Reset to plan v1
        </Button>
      </div>
      {error && (
        <p role="alert" className="text-body text-destructive">
          {error.message}
        </p>
      )}
    </section>
  );
}
