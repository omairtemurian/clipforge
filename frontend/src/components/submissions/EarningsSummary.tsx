import type { SubmissionView } from "@/api/types";
import { campaignEarnings, formatUsd } from "@/lib/earnings";

interface EarningsSummaryProps {
  submissions: SubmissionView[];
  /** The campaign's rate in USD per 1,000 views, if it has one. */
  rate: number | null;
}

/**
 * The earnings of a campaign (SPEC-v2 3.18): the views its board approved,
 * the estimated earnings from them at the campaign's rate (labeled as an
 * estimate) and the payouts the owner entered.
 */
export function EarningsSummary({ submissions, rate }: EarningsSummaryProps) {
  const earnings = campaignEarnings(submissions, rate);

  return (
    <section aria-label="Earnings" className="flex flex-col gap-2">
      <h3 className="text-body font-medium">Earnings</h3>
      <dl className="flex flex-wrap gap-x-8 gap-y-2 text-body">
        <Stat
          label="Approved views"
          value={earnings.approvedViews.toLocaleString("en-US")}
        />
        <Stat
          label="Estimated earnings"
          value={
            earnings.estimateUsd === null
              ? "No rate set"
              : formatUsd(earnings.estimateUsd)
          }
        />
        <Stat label="Payouts" value={formatUsd(earnings.payoutsUsd)} />
      </dl>
      <p className="text-caption text-muted-foreground">
        {rate === null
          ? "Add the campaign's rate to estimate earnings."
          : `Estimate: approved views / 1,000 × ${formatUsd(rate)}. The board's payout is what counts.`}
      </p>
    </section>
  );
}

/** One figure of the summary. */
function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-caption text-muted-foreground">{label}</dt>
      <dd className="text-section font-semibold">{value}</dd>
    </div>
  );
}
