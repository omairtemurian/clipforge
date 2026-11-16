import { describe, expect, it } from "vitest";
import type { SubmissionView } from "@/api/types";
import {
  answerOptions,
  detailsOf,
  detailsPatch,
  detailsProblems,
  statusTone,
} from "./submissions";

function submission(overrides: Partial<SubmissionView> = {}): SubmissionView {
  return {
    id: 1,
    post_id: 1,
    campaign_id: 1,
    submitted_at: null,
    answered_at: null,
    status: "submitted",
    approved_views: null,
    payout_usd: null,
    notes: "",
    platform: "youtube",
    post_url: "https://youtu.be/abc",
    clip_id: 1,
    clip_title: "Clip",
    campaign_name: "Whop clips",
    copy_text: "https://youtu.be/abc",
    ...overrides,
  };
}

describe("submissions lib", () => {
  it("offers the current status then the board's answers", () => {
    expect(answerOptions("submitted")).toEqual([
      "submitted",
      "approved",
      "rejected",
    ]);
    expect(answerOptions("approved")).toEqual(["approved", "rejected", "paid"]);
    expect(answerOptions("paid")).toEqual(["paid", "approved"]);
    expect(answerOptions("not_submitted")).toEqual(["not_submitted"]);
  });

  it("picks a tone per status", () => {
    expect(statusTone("not_submitted")).toBe("neutral");
    expect(statusTone("submitted")).toBe("primary");
    expect(statusTone("rejected")).toBe("danger");
    expect(statusTone("paid")).toBe("success");
  });

  it("flags numbers that are not allowed", () => {
    const draft = { ...detailsOf(submission()), views: "1.5", payout: "-2" };
    expect(detailsProblems(draft).views).toBeDefined();
    expect(detailsProblems(draft).payout).toBeDefined();
    const fine = { ...draft, views: "1200", payout: "12.5" };
    expect(detailsProblems(fine)).toEqual({
      views: undefined,
      payout: undefined,
    });
  });

  it("patches only what changed, blank numbers as null", () => {
    const saved = submission({ approved_views: 100, notes: "ok" });
    expect(detailsPatch(saved, detailsOf(saved))).toEqual({});
    const draft = {
      ...detailsOf(saved),
      status: "approved" as const,
      views: "",
      payout: "3.5",
    };
    expect(detailsPatch(saved, draft)).toEqual({
      status: "approved",
      approved_views: null,
      payout_usd: 3.5,
    });
  });
});
