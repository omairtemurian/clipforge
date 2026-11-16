import type { Campaign, CampaignCheck } from "@/api/types";

/** A saved campaign as the API returns it (permission still missing). */
export function campaign(overrides: Partial<Campaign> = {}): Campaign {
  return {
    id: 1,
    permission_screenshot_asset_id: null,
    permission_checked_at: null,
    name: "Whop clips",
    creator_name: "Afro",
    source_channel_urls: ["https://www.youtube.com/@afro"],
    platform_board: "whop",
    campaign_url: null,
    permission_source_url: null,
    badge: "open",
    rate_per_1k_usd: 0.5,
    budget_note: "",
    allowed_platforms: ["youtube", "tiktok"],
    required_hashtags: ["afro", "clips"],
    required_credit_line: "Clip from Afro",
    required_tags_mentions: ["@afro"],
    min_duration_s: 20,
    max_duration_s: 60,
    banned_content_notes: "",
    monetization_allowed_elsewhere: null,
    submission_instructions: "",
    status: "active",
    notes: "",
    end_date: null,
    caption_template: null,
    allow_heavy_edits: "unknown",
    permission_complete: false,
    ...overrides,
  };
}

/** The rule check of a clip: hashtags fail, the other rules pass. */
export function failingCheck(clipId = 7): CampaignCheck {
  return {
    clip_id: clipId,
    campaign_id: 1,
    platform: null,
    passed: false,
    results: [
      {
        rule: "campaign_status",
        passed: true,
        detail: "The campaign is active.",
      },
      { rule: "source_rights", passed: true, detail: "Source rights: own." },
      {
        rule: "hashtags",
        passed: false,
        detail: "Missing hashtags: #afro. Add them to the clip.",
      },
    ],
  };
}
