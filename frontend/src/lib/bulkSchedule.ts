/**
 * The bulk scheduler dialog (SPEC-v2 3.10): several clips to several
 * accounts at once. Each platform's text is the same for every clip; a
 * blank title, caption or hashtags field means each clip's own.
 */
import type { PostTarget, PostText, SocialAccount } from "@/api/types";
import { parseHashtags } from "@/lib/clipText";
import {
  POST_PLATFORMS,
  PRIVACY_CHOICES,
  canPost,
  hasTitle,
  platformsOf,
  type PostDrafts,
  type PostFields,
  type PostPlatform,
} from "@/lib/postForm";

/** A platform's fields before anything is typed (each clip's own texts,
 * the platform's first privacy; TikTok has to be chosen). */
export function blankFields(platform: PostPlatform): PostFields {
  return {
    title: "",
    caption: "",
    hashtags: "",
    privacy: platform === "tiktok" ? "" : PRIVACY_CHOICES[platform][0].value,
  };
}

/** Every platform's blank fields. */
export function blankDrafts(): PostDrafts {
  const entries = POST_PLATFORMS.map((p) => [p, blankFields(p)] as const);
  return Object.fromEntries(entries) as PostDrafts;
}

/** The PostText of a platform's fields: blank fields take each clip's own. */
export function bulkText(platform: PostPlatform, fields: PostFields): PostText {
  const title = fields.title.trim();
  const hashtags = parseHashtags(fields.hashtags);
  return {
    title: hasTitle(platform) && title ? title : null,
    caption: fields.caption.trim() ? fields.caption : null,
    hashtags: hashtags.length > 0 ? hashtags : null,
    link: null,
    privacy: fields.privacy || null,
    collaborators: [],
    options: {},
  };
}

/** A target per chosen account with its platform's text. */
export function bulkTargets(
  accounts: SocialAccount[],
  drafts: PostDrafts,
): PostTarget[] {
  return accounts.filter(canPost).map((account) => {
    const platform = account.platform as PostPlatform;
    return {
      account_id: account.id,
      text: bulkText(platform, drafts[platform]),
    };
  });
}

/** What keeps the bulk posts from being scheduled, or null. */
export function bulkProblem(
  clipIds: readonly number[],
  accounts: SocialAccount[],
  drafts: PostDrafts,
): string | null {
  if (clipIds.length === 0) return "Choose the clips to post.";
  if (accounts.length === 0) return "Choose an account to post to.";
  if (platformsOf(accounts).includes("tiktok") && !drafts.tiktok.privacy) {
    return "Choose who can see the TikTok posts.";
  }
  return null;
}

/** "6 posts": one per clip per account. */
export function postCountLabel(clips: number, accounts: number): string {
  const count = clips * accounts;
  return count === 1 ? "1 post" : `${count} posts`;
}
