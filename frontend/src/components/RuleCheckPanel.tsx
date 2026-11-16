import { useCampaignCheck } from "@/api/campaigns";
import { cn } from "@/lib/utils";
import { RuleResultList } from "./RuleResultList";

/**
 * The rule checker for a clip: pass or fail for each rule of its project's
 * campaign, with what was found or what to fix. Publishing is blocked while
 * a rule fails. A project without a campaign only has the source rights rule.
 */
export function RuleCheckPanel({ clipId }: { clipId: number }) {
  const check = useCampaignCheck(clipId);

  if (check.isPending) {
    return (
      <p className="text-body text-muted-foreground">Checking the rules…</p>
    );
  }
  if (check.isError) {
    return (
      <p role="alert" className="text-body text-destructive">
        Could not check the rules.
      </p>
    );
  }
  const { results, passed, campaign_id } = check.data;

  return (
    <div className="flex flex-col gap-3">
      <p
        role="status"
        className={cn(
          "rounded-lg px-3 py-2 text-body font-medium",
          passed
            ? "bg-success/10 text-success"
            : "bg-destructive/10 text-destructive",
        )}
      >
        {passed
          ? "All rules pass. This clip can be published."
          : "A rule fails. Publishing is blocked until it is fixed."}
      </p>
      {campaign_id === null && (
        <p className="text-caption text-muted-foreground">
          The project has no campaign: choose one in the project's gallery to
          check its rules.
        </p>
      )}
      <RuleResultList results={results} />
    </div>
  );
}
