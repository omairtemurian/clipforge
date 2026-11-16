/**
 * The one-click "Post" button (owner request 2026-11-02): which accounts
 * the sheet starts with (each platform's default account, for the
 * platforms posted to last) and the platforms remembered between posts.
 */
import type { SocialAccount } from "@/api/types";
import { POST_PLATFORMS, canPost, type PostPlatform } from "@/lib/postForm";

const STORAGE_KEY = "clipforge.quickPost.platforms";

/** The platforms the user posted to last, [] if none is remembered. */
export function lastPlatforms(storage: Storage = localStorage): PostPlatform[] {
  try {
    const saved: unknown = JSON.parse(storage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(saved)
      ? POST_PLATFORMS.filter((platform) => saved.includes(platform))
      : [];
  } catch {
    return [];
  }
}

/** Remember the platforms of a post. */
export function rememberPlatforms(
  platforms: readonly PostPlatform[],
  storage: Storage = localStorage,
): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(platforms));
  } catch {
    // A full or blocked storage only forgets the choice.
  }
}

/** The account a quick post uses on each platform: the one starred as the
 * default, else the oldest. */
export function defaultAccounts(accounts: SocialAccount[]): SocialAccount[] {
  return POST_PLATFORMS.flatMap((platform) => {
    const ofPlatform = accounts.filter(
      (account) => account.platform === platform,
    );
    const chosen = ofPlatform.find((account) => account.is_default);
    const account = chosen ?? ofPlatform[0];
    return account ? [account] : [];
  });
}

/** The ids the sheet starts with: the default accounts of the platforms
 * posted to last, or of every platform if none of those has one. */
export function startingIds(
  accounts: SocialAccount[],
  remembered: readonly PostPlatform[],
): Set<number> {
  const defaults = defaultAccounts(accounts.filter(canPost));
  const last = defaults.filter((account) =>
    remembered.includes(account.platform as PostPlatform),
  );
  return new Set((last.length > 0 ? last : defaults).map((a) => a.id));
}
