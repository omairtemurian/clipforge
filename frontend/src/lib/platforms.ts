import type { PlatformStatus, SocialAccount } from "@/api/types";

export type SocialPlatform = SocialAccount["platform"];

export const PLATFORM_LABELS: Record<SocialPlatform, string> = {
  youtube: "YouTube",
  tiktok: "TikTok",
  instagram: "Instagram",
  facebook: "Facebook",
  x: "X",
  linkedin: "LinkedIn",
};

/** The name of a platform as the user knows it. */
export function platformLabel(platform: SocialPlatform): string {
  return PLATFORM_LABELS[platform];
}

/** The text of a platform's sign-in button: YouTube signs in with the
 * Google account. */
export function signInLabel(platform: SocialPlatform): string {
  return `Sign in with ${platform === "youtube" ? "Google" : platformLabel(platform)}`;
}

/** The platforms ClipForge can publish to, in the order of the API. */
export function supportedPlatforms(
  statuses: PlatformStatus[] | undefined,
): PlatformStatus[] {
  return (statuses ?? []).filter((status) => status.supported);
}

/** The line that says which keys a platform's developer app still needs. */
export function missingKeysLine(status: PlatformStatus): string {
  const keys = status.settings_keys.join(" and ");
  return `Set ${keys} in .env.local (your own ${platformLabel(status.platform)} developer app) and restart ClipForge.`;
}
