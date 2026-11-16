import type { Post, SocialAccount } from "@/api/types";

/** A connected account as the API returns it. */
export function socialAccount(
  overrides: Partial<SocialAccount> = {},
): SocialAccount {
  return {
    id: 1,
    platform: "youtube",
    external_id: "UC1",
    display_name: "Main channel",
    token_ref: "ref1",
    scopes: [],
    connected_at: "2026-10-31T10:00:00Z",
    restrictions: [],
    is_default: false,
    avatar_url: null,
    always_hashtags: [],
    ...overrides,
  };
}

/** A post as the API returns it (scheduled on YouTube by default). */
export function post(overrides: Partial<Post> = {}): Post {
  return {
    id: 1,
    clip_id: 7,
    account_id: 1,
    platform: "youtube",
    payload: { title: "Pizza night", description: "A whole pizza." },
    thumbnail_asset_id: null,
    scheduled_at: "2030-01-14T08:00:00Z",
    status: "queued",
    external_post_id: null,
    url: null,
    error: null,
    attempts: 0,
    attempted_at: null,
    next_attempt_at: null,
    ...overrides,
  };
}

/** The ISO time of a local wall-clock time (tests run in any timezone). */
export function localIso(
  year: number,
  month: number,
  day: number,
  hour = 9,
  minute = 0,
): string {
  return new Date(year, month - 1, day, hour, minute).toISOString();
}
