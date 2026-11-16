import { describe, expect, it } from "vitest";
import type { SubmissionView } from "@/api/types";
import { campaignEarnings, formatUsd } from "./earnings";

function submission(
  status: SubmissionView["status"],
  approved_views: number | null,
  payout_usd: number | null = null,
): SubmissionView {
  return {
    id: 1,
    post_id: 1,
    campaign_id: 1,
    submitted_at: null,
    answered_at: null,
    status,
    approved_views,
    payout_usd,
    notes: "",
    platform: "youtube",
    post_url: "https://youtu.be/a",
    clip_id: 1,
    clip_title: "Clip",
    campaign_name: "Campaign",
    copy_text: "",
  };
}

describe("campaignEarnings", () => {
  it("estimates approved and paid views at the rate and sums the payouts", () => {
    const earnings = campaignEarnings(
      [
        submission("approved", 12_345),
        submission("paid", 2_000, 4.5),
        submission("submitted", 9_999),
        submission("rejected", 700, 1),
        submission("approved", null),
      ],
      2.5,
    );
    expect(earnings).toEqual({
      approvedViews: 14_345,
      estimateUsd: 35.8625,
      payoutsUsd: 5.5,
    });
  });

  it("has no estimate without a rate", () => {
    expect(campaignEarnings([submission("paid", 1_000)], null)).toEqual({
      approvedViews: 1_000,
      estimateUsd: null,
      payoutsUsd: 0,
    });
  });
});

describe("formatUsd", () => {
  it("writes dollars with cents and thousands", () => {
    expect(formatUsd(30.8625)).toBe("$30.86");
    expect(formatUsd(1234.5)).toBe("$1,234.50");
    expect(formatUsd(0)).toBe("$0.00");
  });
});
