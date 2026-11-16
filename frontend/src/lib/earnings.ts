import type { SubmissionView } from "@/api/types";

/** What a campaign's submissions earned so far. */
export interface Earnings {
  /** Views the board approved, on approved and paid submissions. */
  approvedViews: number;
  /** approvedViews / 1,000 x the rate; null when the campaign has no rate. */
  estimateUsd: number | null;
  /** The payouts the owner entered. */
  payoutsUsd: number;
}

const COUNTED: SubmissionView["status"][] = ["approved", "paid"];

/**
 * The earnings of a campaign's submissions at `rate` USD per 1,000 views:
 * the estimate counts the approved views of approved and paid submissions
 * (as the daily digest does), the payouts are every payout entered.
 */
export function campaignEarnings(
  submissions: SubmissionView[],
  rate: number | null,
): Earnings {
  const approvedViews = submissions
    .filter((s) => COUNTED.includes(s.status))
    .reduce((sum, s) => sum + (s.approved_views ?? 0), 0);
  const payoutsUsd = submissions.reduce(
    (sum, s) => sum + (s.payout_usd ?? 0),
    0,
  );
  return {
    approvedViews,
    estimateUsd: rate === null ? null : (approvedViews * rate) / 1000,
    payoutsUsd,
  };
}

const USD = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

/** An amount in US dollars, e.g. "$1,234.56". */
export function formatUsd(amount: number): string {
  return USD.format(amount);
}
