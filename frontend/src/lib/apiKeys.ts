import type { ApiKey } from "@/api/types";
import { parseApiDate, timeAgo } from "./format";

/** How far back a key's last request counts as "connected recently". */
export const RECENT_DAYS = 7;
const DAY_MS = 24 * 60 * 60 * 1000;

/** The keys used in the last RECENT_DAYS days, most recently used first. */
export function recentlyUsed(keys: ApiKey[], now: Date = new Date()): ApiKey[] {
  const since = now.getTime() - RECENT_DAYS * DAY_MS;
  return keys
    .filter(
      (key) =>
        key.last_used_at !== null &&
        parseApiDate(key.last_used_at).getTime() >= since,
    )
    .sort(
      (a, b) =>
        parseApiDate(b.last_used_at ?? "").getTime() -
        parseApiDate(a.last_used_at ?? "").getTime(),
    );
}

/** "Last used 5 min ago" or "Never used". */
export function lastUsedLabel(key: ApiKey, now: Date = new Date()): string {
  return key.last_used_at === null
    ? "Never used"
    : `Last used ${timeAgo(key.last_used_at, now)}`;
}
