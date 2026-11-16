/**
 * The posting calendar (SPEC-v2 3.10): the days of a month or week view
 * (weeks start on Sunday, in the browser's timezone), which day each post
 * falls on, what its card says and the filters of the page.
 */
import type { Post, SocialAccount } from "@/api/types";
import type { PillTone } from "@/components/ui/pill";
import { parseApiDate } from "@/lib/format";
import type { SocialPlatform } from "@/lib/platforms";

export type CalendarView = "month" | "week";
export type PostStatus = Post["status"];

/** Cards a day shows before "See N more". */
export const DAY_CARD_LIMIT = 3;

export const STATUS_LABELS: Record<PostStatus, string> = {
  draft: "Draft",
  queued: "Scheduled",
  uploading: "Posting",
  published: "Posted",
  failed: "Failed",
  canceled: "Canceled",
  skipped: "Skipped",
};

/** The pill tone of a status (Posted green, Failed red, Draft ember,
 * Skipped amber). */
export const STATUS_TONES: Record<PostStatus, PillTone> = {
  draft: "primary",
  queued: "neutral",
  uploading: "neutral",
  published: "success",
  failed: "danger",
  canceled: "neutral",
  skipped: "warning",
};

export interface CalendarFilters {
  platform: SocialPlatform | "all";
  accountId: number | "all";
  status: PostStatus | "all";
}

export const NO_FILTERS: CalendarFilters = {
  platform: "all",
  accountId: "all",
  status: "all",
};

/** The local day of a date as "yyyy-mm-dd". */
export function dayKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Midnight (local) of the day of date. */
function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

/** The date n days after date (local days, DST-safe). */
function addDays(date: Date, n: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);
}

/** The Sunday-to-Saturday week that contains date. */
export function weekDays(date: Date): Date[] {
  const sunday = addDays(startOfDay(date), -date.getDay());
  return Array.from({ length: 7 }, (_, i) => addDays(sunday, i));
}

/** The weeks (Sunday first) that cover the month of date. */
export function monthWeeks(date: Date): Date[][] {
  const first = new Date(date.getFullYear(), date.getMonth(), 1);
  const last = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  const weeks: Date[][] = [];
  for (
    let sunday = weekDays(first)[0];
    sunday <= last;
    sunday = addDays(sunday, 7)
  ) {
    weeks.push(weekDays(sunday));
  }
  return weeks;
}

/** The anchor date moved by one month or week (step = 1 or -1). */
export function shiftAnchor(
  date: Date,
  view: CalendarView,
  step: number,
): Date {
  return view === "month"
    ? new Date(date.getFullYear(), date.getMonth() + step, 1)
    : addDays(startOfDay(date), 7 * step);
}

/** The title of the shown range: "November 2026", or the week's days. */
export function rangeTitle(date: Date, view: CalendarView): string {
  if (view === "month") {
    return date.toLocaleDateString(undefined, {
      month: "long",
      year: "numeric",
    });
  }
  const days = weekDays(date);
  const first = days[0].toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
  const last = days[6].toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  return `${first} – ${last}`;
}

/** The day label of a cell: "Nov 2". */
export function dayLabel(date: Date): string {
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/** The time of day of a post card: "6:00 PM". */
export function timeLabel(date: Date): string {
  return date.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
}

/** When the post is on the calendar: its scheduled time, else when it was
 * last sent (posted right away); null for an unscheduled draft. */
export function postTime(post: Post): Date | null {
  const at = post.scheduled_at ?? post.attempted_at ?? null;
  return at ? parseApiDate(at) : null;
}

/** The one line a card shows: the post's title, else its caption. */
export function postTitle(post: Post): string {
  const payload = post.payload as Record<string, unknown>;
  for (const key of ["title", "caption", "description"]) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim().split("\n")[0];
    }
  }
  return "Untitled post";
}

/** Whether the post can be dragged to another day (only scheduled ones). */
export function canDrag(post: Post): boolean {
  return post.status === "queued";
}

/** The posts that pass the filters; canceled posts only when asked for. */
export function filterPosts(posts: Post[], filters: CalendarFilters): Post[] {
  return posts.filter(
    (post) =>
      (filters.status === "all"
        ? post.status !== "canceled"
        : post.status === filters.status) &&
      (filters.platform === "all" || post.platform === filters.platform) &&
      (filters.accountId === "all" || post.account_id === filters.accountId),
  );
}

/** The posts of each local day ("yyyy-mm-dd"), earliest first. */
export function postsByDay(posts: Post[]): Map<string, Post[]> {
  const timed = posts
    .map((post) => ({ post, at: postTime(post) }))
    .filter((each): each is { post: Post; at: Date } => each.at !== null)
    .sort((a, b) => a.at.getTime() - b.at.getTime() || a.post.id - b.post.id);
  const days = new Map<string, Post[]>();
  for (const { post, at } of timed) {
    const key = dayKey(at);
    days.set(key, [...(days.get(key) ?? []), post]);
  }
  return days;
}

/** The time a post dropped on day goes out: the same local time of day. */
export function movedTime(at: Date, day: Date): Date {
  return new Date(
    day.getFullYear(),
    day.getMonth(),
    day.getDate(),
    at.getHours(),
    at.getMinutes(),
    at.getSeconds(),
  );
}

/** The accounts by id, for the cards' names and avatars. */
export function accountsById(
  accounts: SocialAccount[] | undefined,
): Map<number, SocialAccount> {
  return new Map((accounts ?? []).map((account) => [account.id, account]));
}

/** The value of a datetime-local input showing date (local time). */
export function localInputValue(date: Date): string {
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${dayKey(date)}T${hours}:${minutes}`;
}
