/**
 * The posting history (SPEC-v2 3.10): what each finished post says about
 * when it went out, failed or was skipped, and the history's filters.
 */
import type { HistoryStatus } from "@/api/posts";
import type { Post } from "@/api/types";
import { parseApiDate } from "@/lib/format";

export type HistoryFilter = HistoryStatus | "all";

/** The status filter of the history page, in its order. */
export const HISTORY_FILTERS: { value: HistoryFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "published", label: "Posted" },
  { value: "failed", label: "Failed" },
  { value: "skipped", label: "Skipped" },
];

/** How many posts the history shows at first, and adds per "Show more". */
export const HISTORY_PAGE = 50;

/** The moment of a post in the history: when its latest upload started,
 * or its scheduled time if it was never tried. */
export function historyTime(post: Post): Date | null {
  const iso = post.attempted_at ?? post.scheduled_at;
  return iso ? parseApiDate(iso) : null;
}

/** "Posted Nov 2, 2026, 3:04 PM", "Failed …" or "Skipped, was due …". */
export function historyWhen(post: Post): string {
  const at = historyTime(post);
  const time = at
    ? at.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : null;
  const verb =
    post.status === "published"
      ? "Posted"
      : post.status === "skipped"
        ? "Skipped, was due"
        : "Failed";
  return time ? `${verb} ${time}` : verb;
}
