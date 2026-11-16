/**
 * The campaign form: its draft (the lists are pasted text), the checks that
 * mirror the API's (models.CampaignCreate) and the JSON body.
 */
import type { Campaign, CampaignCreate } from "@/api/types";

export const TEXT_MAX = 2000;
export const CREDIT_MAX = 200;
export const SCREENSHOT_MAX_BYTES = 5 * 1024 * 1024;
export const SCREENSHOT_TYPES = ["image/png", "image/jpeg", "image/webp"];

export type Platform = Campaign["allowed_platforms"][number];
export type Unknown3 = "unknown" | "yes" | "no";

export interface CampaignDraft {
  name: string;
  creator: string;
  channelUrls: string;
  board: Campaign["platform_board"];
  campaignUrl: string;
  badge: Campaign["badge"];
  rate: string;
  budgetNote: string;
  platforms: Platform[];
  hashtags: string;
  creditLine: string;
  mentions: string;
  minDuration: string;
  maxDuration: string;
  banned: string;
  monetization: Unknown3;
  instructions: string;
  status: Campaign["status"];
  notes: string;
  endDate: string;
  captionTemplate: string;
  /** Kept as saved: the heavy-edits switch has no field in the form yet. */
  allowHeavyEdits: Campaign["allow_heavy_edits"];
  permissionUrl: string;
  /** A newly picked permission screenshot; null keeps the saved one. */
  screenshot: File | null;
}

export type CampaignProblems = Partial<
  Record<
    | "name"
    | "channelUrls"
    | "campaignUrl"
    | "permissionUrl"
    | "rate"
    | "minDuration"
    | "maxDuration"
    | "screenshot"
    | "hashtags"
    | "mentions",
    string
  >
>;

/** A draft with the values of a new campaign, or those of `campaign`. */
export function draftOf(campaign?: Campaign): CampaignDraft {
  const monetization = campaign?.monetization_allowed_elsewhere;
  return {
    name: campaign?.name ?? "",
    creator: campaign?.creator_name ?? "",
    channelUrls: (campaign?.source_channel_urls ?? []).join("\n"),
    board: campaign?.platform_board ?? "other",
    campaignUrl: campaign?.campaign_url ?? "",
    badge: campaign?.badge ?? "open",
    rate: campaign?.rate_per_1k_usd?.toString() ?? "",
    budgetNote: campaign?.budget_note ?? "",
    platforms: campaign?.allowed_platforms ?? [],
    hashtags: (campaign?.required_hashtags ?? []).map((t) => `#${t}`).join(" "),
    creditLine: campaign?.required_credit_line ?? "",
    mentions: (campaign?.required_tags_mentions ?? []).join(" "),
    minDuration: campaign?.min_duration_s?.toString() ?? "",
    maxDuration: campaign?.max_duration_s?.toString() ?? "",
    banned: campaign?.banned_content_notes ?? "",
    monetization:
      monetization === undefined || monetization === null
        ? "unknown"
        : monetization
          ? "yes"
          : "no",
    instructions: campaign?.submission_instructions ?? "",
    status: campaign?.status ?? "active",
    notes: campaign?.notes ?? "",
    endDate: campaign?.end_date ?? "",
    captionTemplate: campaign?.caption_template ?? "",
    allowHeavyEdits: campaign?.allow_heavy_edits ?? "unknown",
    permissionUrl: campaign?.permission_source_url ?? "",
    screenshot: null,
  };
}

/** The pieces of pasted text: split on whitespace and commas. */
export function pastedTags(text: string): string[] {
  return text.split(/[\s,]+/).filter((tag) => tag.length > 0);
}

/** The lines of pasted text, without empty ones. */
export function pastedLines(text: string): string[] {
  return text
    .split(/[\r\n]+/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function isUrl(text: string): boolean {
  try {
    const { protocol } = new URL(text);
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
}

function numberProblem(text: string, name: string): string | undefined {
  if (text.trim() === "") return undefined;
  const value = Number(text);
  if (!Number.isFinite(value) || value <= 0) return `${name} must be over 0.`;
  return undefined;
}

function screenshotProblem(file: File): string | undefined {
  if (!SCREENSHOT_TYPES.includes(file.type))
    return "Use a PNG, JPEG or WebP image.";
  if (file.size === 0) return "The file is empty.";
  if (file.size > SCREENSHOT_MAX_BYTES)
    return "The image must be 5 MB or smaller.";
  return undefined;
}

/** What is wrong with draft, by field (a field that is fine is absent). */
export function validateCampaign(draft: CampaignDraft): CampaignProblems {
  const problems: CampaignProblems = {};
  if (draft.name.trim() === "") problems.name = "Give the campaign a name.";
  if (pastedLines(draft.channelUrls).some((url) => !isUrl(url)))
    problems.channelUrls = "Put one http(s) link per line.";
  if (draft.campaignUrl.trim() !== "" && !isUrl(draft.campaignUrl.trim()))
    problems.campaignUrl = "Use an http(s) link.";
  if (draft.permissionUrl.trim() !== "" && !isUrl(draft.permissionUrl.trim()))
    problems.permissionUrl = "Use an http(s) link.";
  if (
    draft.rate.trim() !== "" &&
    !(Number.isFinite(Number(draft.rate)) && Number(draft.rate) >= 0)
  )
    problems.rate = "The rate must be 0 or more.";
  const low = numberProblem(draft.minDuration, "The minimum");
  if (low) problems.minDuration = low;
  const high = numberProblem(draft.maxDuration, "The maximum");
  if (high) problems.maxDuration = high;
  if (
    !low &&
    !high &&
    draft.minDuration.trim() !== "" &&
    draft.maxDuration.trim() !== "" &&
    Number(draft.minDuration) > Number(draft.maxDuration)
  )
    problems.minDuration = "The minimum must not be over the maximum.";
  if (pastedTags(draft.hashtags).length > 30)
    problems.hashtags = "At most 30 hashtags.";
  if (pastedTags(draft.mentions).length > 30)
    problems.mentions = "At most 30 tags or mentions.";
  if (draft.screenshot) {
    const problem = screenshotProblem(draft.screenshot);
    if (problem) problems.screenshot = problem;
  }
  return problems;
}

function orNull(text: string): string | null {
  const tidy = text.trim();
  return tidy === "" ? null : tidy;
}

function numberOrNull(text: string): number | null {
  return text.trim() === "" ? null : Number(text);
}

/** The body of POST or PATCH /campaigns for draft. */
export function campaignBody(draft: CampaignDraft): CampaignCreate {
  return {
    name: draft.name.trim(),
    creator_name: draft.creator.trim(),
    source_channel_urls: pastedLines(draft.channelUrls),
    platform_board: draft.board,
    campaign_url: orNull(draft.campaignUrl),
    permission_source_url: orNull(draft.permissionUrl),
    badge: draft.badge,
    rate_per_1k_usd: numberOrNull(draft.rate),
    budget_note: draft.budgetNote.trim(),
    allowed_platforms: draft.platforms,
    required_hashtags: pastedTags(draft.hashtags).map((tag) =>
      tag.replace(/^#+/, ""),
    ),
    required_credit_line: draft.creditLine.trim(),
    required_tags_mentions: pastedTags(draft.mentions),
    min_duration_s: numberOrNull(draft.minDuration),
    max_duration_s: numberOrNull(draft.maxDuration),
    banned_content_notes: draft.banned.trim(),
    monetization_allowed_elsewhere:
      draft.monetization === "unknown" ? null : draft.monetization === "yes",
    submission_instructions: draft.instructions.trim(),
    status: draft.status,
    notes: draft.notes.trim(),
    end_date: orNull(draft.endDate),
    caption_template: orNull(draft.captionTemplate),
    allow_heavy_edits: draft.allowHeavyEdits,
  };
}

/** The fields of draft that differ from the saved campaign (the body of
 * PATCH /campaigns/{id}: an unchanged permission URL must not reset the
 * permission date). */
export function campaignChanges(
  draft: CampaignDraft,
  saved: Campaign,
): Partial<CampaignCreate> {
  const body = campaignBody(draft);
  return Object.fromEntries(
    Object.entries(body).filter(
      ([key, value]) =>
        // The Pro Edit section saves allow_heavy_edits; a stale draft of the
        // form must not undo it.
        key !== "allow_heavy_edits" &&
        JSON.stringify(value) !==
          JSON.stringify(saved[key as keyof CampaignCreate]),
    ),
  );
}
