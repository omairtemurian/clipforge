import type { Draft, DraftApproval, RuleResult } from "@/api/types";
import { post } from "./postFixtures";

/** Every rule of a campaign passes. */
export const PASSING_RULES: RuleResult[] = [
  { rule: "campaign_status", passed: true, detail: "The campaign is active." },
  { rule: "source_rights", passed: true, detail: "Source rights: permission." },
  { rule: "hashtags", passed: true, detail: "Has #afro #clips." },
];

/** The hashtags rule fails, the others pass. */
export const FAILING_RULES: RuleResult[] = [
  PASSING_RULES[0],
  PASSING_RULES[1],
  {
    rule: "hashtags",
    passed: false,
    detail: "Missing hashtags: #afro. Add them to the clip.",
  },
];

/** A pending draft of clip 3 (campaign 1) as the API returns it. */
export function draft(overrides: Partial<Draft> = {}): Draft {
  return {
    id: 11,
    clip_id: 3,
    campaign_id: 1,
    status: "pending",
    rule_results: PASSING_RULES,
    reject_reason: null,
    decided_at: null,
    created_at: "2026-11-02T08:00:00",
    notes: [],
    ...overrides,
  };
}

/** The answer of POST /drafts/{id}/approve: one post queued for a slot. */
export function approval(
  approved: Draft,
  scheduledAt = "2030-01-14T08:00:00Z",
): DraftApproval {
  return {
    draft: { ...approved, status: "approved" },
    posts: [
      post({
        clip_id: approved.clip_id,
        status: "queued",
        scheduled_at: scheduledAt,
      }),
    ],
  };
}
