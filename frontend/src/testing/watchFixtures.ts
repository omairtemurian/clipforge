import type {
  WatchEvent,
  WatchStatus,
  WatchedChannel,
  WatchedStreamer,
} from "@/api/types";
import { DEFAULTS, json, type Handler } from "@/testing/mockApi";

export const CHANNEL_ID = "UCBR8-60-B28hp2BmDPdntcQ";

export const POLLING: WatchStatus = {
  push_available: false,
  poll_interval_s: 60,
  twitch_configured: true,
  handles_supported: true,
};

/** A watched YouTube channel as the API returns it. */
export function watchedChannel(
  overrides: Partial<WatchedChannel> = {},
): WatchedChannel {
  return {
    id: 1,
    channel_id: CHANNEL_ID,
    title: "YouTube",
    settings: { ...DEFAULTS, genre: "comedy", num_clips: 3 },
    source_rights: "permission",
    credit_line: "Video by YouTube",
    auto_schedule_drafts: false,
    enabled: true,
    last_checked_at: "2026-10-31T11:55:00",
    last_error: null,
    created_at: "2026-10-31T10:00:00",
    push_state: "off",
    push_lease_expires_at: null,
    push_requested_at: null,
    push_error: null,
    campaign_id: null,
    ...overrides,
  };
}

/** A watched Twitch streamer as the API returns it. */
export function streamer(
  overrides: Partial<WatchedStreamer> = {},
): WatchedStreamer {
  return {
    id: 5,
    login: "afro",
    user_id: "101051819",
    display_name: "Afro",
    enabled: true,
    push_state: "off",
    push_requested_at: null,
    push_error: null,
    subscription_id: null,
    live_since: null,
    last_live_at: null,
    last_checked_at: null,
    last_error: null,
    created_at: "2026-10-31T10:00:00",
    ...overrides,
  };
}

/** An alert: a new upload published 42 s before it was detected. */
export function watchEvent(overrides: Partial<WatchEvent> = {}): WatchEvent {
  return {
    id: 1,
    platform: "youtube",
    kind: "upload",
    external_id: "abc123",
    source_name: "YouTube",
    title: "Big news",
    url: "https://www.youtube.com/watch?v=abc123",
    project_id: 7,
    published_at: "2026-10-31T14:00:00",
    detected_at: "2026-10-31T14:00:42",
    via: "push",
    ...overrides,
  };
}

/** The read-only watch routes of the Watchlist page. */
export function watchRoutes(
  status: WatchStatus = POLLING,
  streamers: WatchedStreamer[] = [],
  events: WatchEvent[] = [],
): Record<string, Handler> {
  return {
    "GET /api/watch/status": () => json(status),
    "GET /api/watch/streamers": () => json(streamers),
    "GET /api/watch/events?limit=20": () => json(events),
  };
}
