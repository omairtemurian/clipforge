import { PaperPlaneTiltIcon } from "@phosphor-icons/react";
import { useSubmissions } from "@/api/submissions";
import { EarningsSummary } from "@/components/submissions/EarningsSummary";
import { SubmissionItem } from "@/components/submissions/SubmissionItem";
import { EmptyState } from "@/components/ui/empty-state";

/**
 * The submission tracker of a campaign (SPEC-v2 3.18): its published posts,
 * newest first. The owner copies a post's URL with the campaign's required
 * information, submits it on the campaign board by hand, ticks it here and
 * later enters the board's answer, the approved views and the payout; the
 * earnings summary adds them up at the campaign's `rate` (USD per 1,000
 * views).
 */
export function SubmissionTracker({
  campaignId,
  rate = null,
}: {
  campaignId: number;
  rate?: number | null;
}) {
  const submissions = useSubmissions(campaignId);
  const list = submissions.data ?? [];
  const waiting = list.filter((s) => s.status === "not_submitted").length;

  return (
    <section aria-label="Submissions" className="flex flex-col gap-3">
      <div>
        <h2 className="text-section">Submissions</h2>
        <p className="text-body text-muted-foreground">
          Copy a published post for the campaign board, submit it there yourself
          and tick it here
          {waiting > 0 && ` (${waiting} still to submit)`}.
        </p>
      </div>
      {submissions.isError && (
        <p role="alert" className="text-body text-destructive">
          Could not load the submissions.
        </p>
      )}
      {submissions.isSuccess && list.length === 0 && (
        <EmptyState icon={PaperPlaneTiltIcon} title="Nothing to submit yet">
          Posts of this campaign's clips appear here once they are published.
        </EmptyState>
      )}
      {list.length > 0 && <EarningsSummary submissions={list} rate={rate} />}
      <ul aria-label="Published posts" className="flex flex-col gap-3">
        {list.map((submission) => (
          <SubmissionItem key={submission.id} submission={submission} />
        ))}
      </ul>
    </section>
  );
}
