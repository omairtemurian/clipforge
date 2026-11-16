import type { RuleResult } from "@/api/types";

/** What the owner sees for each campaign rule. */
export const RULE_LABEL: Record<RuleResult["rule"], string> = {
  campaign_status: "Campaign is active",
  permission: "Permission evidence",
  source_rights: "Source rights",
  min_duration: "Minimum length",
  max_duration: "Maximum length",
  hashtags: "Required hashtags",
  credit_line: "Credit line",
  mentions: "Tags and mentions",
  platform: "Allowed platform",
};
