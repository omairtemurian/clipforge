import type { RejectReason } from "@/api/drafts";
import type { Campaign, DraftApproval } from "@/api/types";
import { parseApiDate } from "@/lib/format";

/** The reason chips of a reject, in the order they are shown. */
export const REJECT_REASONS: { value: RejectReason; label: string }[] = [
  { value: "boring", label: "Boring" },
  { value: "out_of_context", label: "Out of context" },
  { value: "bad_crop", label: "Bad crop" },
  { value: "bad_captions", label: "Bad captions" },
  { value: "too_long", label: "Too long" },
  { value: "other", label: "Other" },
];

/** What a campaign pays, e.g. "$0.50 per 1,000 views". */
export function rateLabel(campaign: Pick<Campaign, "rate_per_1k_usd">): string {
  const rate = campaign.rate_per_1k_usd;
  if (rate === null) return "No rate set";
  return `$${rate.toFixed(2)} per 1,000 views`;
}

/**
 * How fresh the source video is: "Uploaded 40 min ago", "Uploaded 5 h ago",
 * "Uploaded 3 days ago"; null when its upload time is unknown.
 */
export function freshnessLabel(
  publishedAt: string | null,
  now: Date = new Date(),
): string | null {
  if (publishedAt === null) return null;
  const minutes = Math.floor(
    (now.getTime() - parseApiDate(publishedAt).getTime()) / 60_000,
  );
  if (Number.isNaN(minutes)) return null;
  if (minutes < 1) return "Uploaded just now";
  if (minutes < 60) return `Uploaded ${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `Uploaded ${hours} h ago`;
  return `Uploaded ${Math.floor(hours / 24)} days ago`;
}

/** What the inbox's keyboard shortcuts do (on the selected draft). */
export interface InboxKeyHandlers {
  approve: () => void;
  reject: () => void;
  edit: () => void;
  /** Select the next (1) or previous (-1) draft. */
  move: (step: 1 | -1) => void;
  /** Close the reject reasons. */
  cancel: () => void;
}

/** Keys typed here are their own: text fields and open dialogs. */
const NOT_SHORTCUTS =
  "input, textarea, select, [contenteditable='true'], [role='dialog']";
const KEY_ACTIONS: Record<string, (handlers: InboxKeyHandlers) => void> = {
  a: (handlers) => handlers.approve(),
  r: (handlers) => handlers.reject(),
  e: (handlers) => handlers.edit(),
  j: (handlers) => handlers.move(1),
  k: (handlers) => handlers.move(-1),
  escape: (handlers) => handlers.cancel(),
};

/**
 * Handle a keydown of the Approval Inbox: A approves, R rejects, E opens the
 * editor, J/K select the next/previous draft and Escape closes the reject
 * reasons. Keys typed into a text field or a dialog, or with cmd/ctrl/alt,
 * are not shortcuts.
 */
export function handleInboxKey(
  event: KeyboardEvent,
  handlers: InboxKeyHandlers,
): void {
  const target = event.target instanceof Element ? event.target : null;
  if (event.defaultPrevented || target?.closest(NOT_SHORTCUTS)) return;
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const action = KEY_ACTIONS[event.key.toLowerCase()];
  if (!action) return;
  event.preventDefault();
  action(handlers);
}

/** The index of the selected draft after a step, kept inside the list. */
export function stepIndex(index: number, step: number, count: number): number {
  if (count === 0) return 0;
  return Math.min(Math.max(index + step, 0), count - 1);
}

/** A scheduled time as "14 Jan 2030, 09:00" (local time). */
function slotLabel(iso: string): string {
  return parseApiDate(iso).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

/** What an approval did: "Approved: 1 post scheduled for 14 Jan 2030,
 * 09:00" ("2 posts scheduled, the first for ..."). */
export function approvalMessage({ posts }: DraftApproval): string {
  const times = posts
    .map((post) => post.scheduled_at)
    .filter((at): at is string => at !== null)
    .sort();
  const count = `${posts.length} ${posts.length === 1 ? "post" : "posts"}`;
  if (times.length === 0) return `Approved: ${count} queued`;
  const first = posts.length === 1 ? " for" : ", the first for";
  return `Approved: ${count} scheduled${first} ${slotLabel(times[0])}`;
}
