import type { EdlItem, ProEditPlan, ProEditRun } from "@/api/types";
import { CriticPanel } from "./CriticPanel";
import { Inspector } from "./Inspector";
import { PlanActions } from "./PlanActions";
import { PlanVersions } from "./PlanVersions";
import { useProEditPlans } from "./planApi";
import { RunNotes } from "./RunNotes";
import { StyleMatchPanel } from "./StyleMatchPanel";

/** The newest run that has critic rounds, if any. */
function latestCriticRun(runs: ProEditRun[]): ProEditRun | undefined {
  return runs.find((run) => run.critic_scores.length > 0);
}

/** The newest run that ended done, if any. */
function latestDoneRun(runs: ProEditRun[]): ProEditRun | undefined {
  return runs.find((run) => run.status === "done");
}

/**
 * Everything of the Pro Edit editor under the lanes (SPEC-v3 3.8): the
 * Director/critic/reset actions, the inspector of the selected item and what
 * post-processing moved or dropped in the latest run, next
 * to the plan version history (with the diff of a version) and the critic's
 * scores and "what changed", and the style-match of a plan with a style
 * recipe.
 */
export function PlanTools({
  variantId,
  plan,
  runs,
  selected,
  busy,
  onApply,
}: {
  variantId: number;
  plan: ProEditPlan;
  runs: ProEditRun[];
  selected: EdlItem | undefined;
  busy: boolean;
  onApply: (item: EdlItem) => void;
}) {
  const plans = useProEditPlans(variantId);
  const done = latestDoneRun(runs);
  return (
    <div className="grid gap-8 lg:grid-cols-2">
      <div className="flex flex-col gap-6">
        <PlanActions variantId={variantId} version={plan.version} busy={busy} />
        <Inspector item={selected} disabled={busy} onApply={onApply} />
        {done && <RunNotes notes={done.notes} />}
      </div>
      <div className="flex flex-col gap-6">
        {plans.data && <PlanVersions plans={plans.data} />}
        <CriticPanel run={latestCriticRun(runs)} />
        {plan.style_recipe_id !== null && (
          <StyleMatchPanel variantId={variantId} />
        )}
      </div>
    </div>
  );
}
