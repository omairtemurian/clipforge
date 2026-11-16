import type { WatchEvent, WatchStatus, WatchedChannel } from "@/api/types";
import { parseApiDate } from "@/lib/format";

export type PushState = WatchedChannel["push_state"];

/** "42 s", "3 min", "2 h 5 min" or "3 d": a duration in words. */
export function durationLabel(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    const rest = minutes % 60;
    return rest ? `${hours} h ${rest} min` : `${hours} h`;
  }
  return `${Math.floor(hours / 24)} d`;
}

/**
 * How an entry is watched: "Push" once the hub or Twitch confirmed the
 * subscription, "Push pending" while it is being confirmed, else "Polling
 * every N s" (with why push is off when it failed).
 */
export function watchModeLabel(
  state: PushState,
  pollIntervalS: number,
): string {
  if (state === "subscribed") return "Push";
  if (state === "pending") return "Push pending";
  const polling = `Polling every ${Math.round(pollIntervalS)} s`;
  return state === "off" ? polling : `${polling} (push ${state})`;
}

/** The line at the top of the Watchlist: push or polling. */
export function watchStatusLine(status: WatchStatus): string {
  if (status.push_available) {
    return "Push is on: YouTube and Twitch notify ClipForge within seconds; feeds are also checked as a fallback.";
  }
  return `Polling every ${Math.round(status.poll_interval_s)} s. Set PUBLIC_CALLBACK_URL (an HTTPS tunnel) for instant push.`;
}

/** The time from publish (or go-live) to detection, or null if unknown. */
export function detectionDelay(event: WatchEvent): string | null {
  if (event.published_at === null) return null;
  return durationLabel(
    parseApiDate(event.detected_at).getTime() -
      parseApiDate(event.published_at).getTime(),
  );
}

/** The title and text of an alert, as shown in the toast and on the
 * desktop. */
export function alertText(event: WatchEvent): { title: string; body: string } {
  const delay = detectionDelay(event);
  if (event.kind === "live") {
    const since = delay ? ` (live for ${delay})` : "";
    return {
      title: `${event.source_name} is live`,
      body: `${event.title || "Live on Twitch"}${since}`,
    };
  }
  const after = delay ? ` (${delay} after publish)` : "";
  return {
    title: `New upload from ${event.source_name}`,
    body: `${event.title || event.external_id}${after}`,
  };
}
