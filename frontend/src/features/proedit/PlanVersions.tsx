import { useState } from "react";
import type { ProEditPlan } from "@/api/types";
import { cn } from "@/lib/utils";
import { diffPlans } from "./planDiff";

const MADE_BY: Record<ProEditPlan["created_by"], string> = {
  director: "Director",
  rule_director: "Rule-based Director",
  user: "You",
  critic_revision: "Critic",
};

const OP_LABEL = { added: "Added", removed: "Removed", changed: "Changed" };

/** What changed from the version before the chosen one (nothing for v1). */
function VersionDiff({
  plan,
  before,
}: {
  plan: ProEditPlan;
  before: ProEditPlan | undefined;
}) {
  if (!before) {
    return (
      <p className="text-body text-muted-foreground">
        The first version has {plan.items.length} items.
      </p>
    );
  }
  const changes = diffPlans(before, plan);
  if (changes.length === 0) {
    return (
      <p className="text-body text-muted-foreground">
        Version {plan.version} changes no item of version {before.version}.
      </p>
    );
  }
  return (
    <ul aria-label={`Changes from v${before.version}`} className="text-body">
      {changes.map((change) => (
        <li key={`${change.op}-${change.itemId}`}>
          <span className="font-medium">{OP_LABEL[change.op]}</span>{" "}
          {change.label} #{change.itemId}
          {change.details.length > 0 && (
            <span className="block text-muted-foreground">
              {change.details.join("; ")}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * The plan version history (SPEC-v3 3.8), newest first: who made each
 * version, and for the chosen one (default the newest) what it changed
 * compared with the version before it.
 */
export function PlanVersions({ plans }: { plans: ProEditPlan[] }) {
  const [chosen, setChosen] = useState<number | null>(null);
  const newest = plans[plans.length - 1];
  const index = plans.findIndex((plan) => plan.version === chosen);
  const at = index >= 0 ? index : plans.length - 1;
  if (!newest) return null;

  return (
    <section aria-label="Version history" className="flex flex-col gap-3">
      <h3 className="text-body font-semibold">Plan versions</h3>
      <ol className="flex flex-col gap-1">
        {[...plans].reverse().map((plan) => (
          <li key={plan.id}>
            <button
              type="button"
              aria-pressed={plan === plans[at]}
              onClick={() => setChosen(plan.version)}
              className={cn(
                "w-full cursor-pointer rounded-md border px-3 py-1.5 text-left text-body",
                plan === plans[at]
                  ? "border-primary bg-primary/10"
                  : "border-border hover:border-foreground/25",
              )}
            >
              v{plan.version}
              <span className="text-muted-foreground">
                {" "}
                · {MADE_BY[plan.created_by]} · {plan.items.length} items
              </span>
            </button>
          </li>
        ))}
      </ol>
      <VersionDiff plan={plans[at]} before={plans[at - 1]} />
    </section>
  );
}
