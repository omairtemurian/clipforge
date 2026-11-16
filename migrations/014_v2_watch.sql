-- 014_v2_watch: fast creator watch (T28c, TASK-195): WebSub push state of
-- the watched YouTube channels, watched Twitch streamers and the watch's
-- alerts (new uploads, go-live).
--
-- watched_channel gains its WebSub subscription: push_state is off (no
-- public callback URL), pending (asked the hub, waiting for its
-- verification), subscribed (verified; push_lease_expires_at is the end of
-- the hub's lease), denied (the hub refused) or failed (the hub request
-- failed: push_error says why). push_requested_at is the time of the last
-- hub request. Existing channels start off.
--
-- watched_streamer: one row per Twitch login. user_id is the broadcaster id
-- (NULL until the Helix users call resolved it); push_state is the EventSub
-- stream.online webhook subscription (subscription_id, its id at Twitch;
-- "revoked" when Twitch revoked it); live_since is set while a poll sees
-- the stream live; last_live_at is the start of the latest live stream.
--
-- watch_event: one row per alert: kind "upload" (a new video; project_id is
-- its project) or "live" (a stream went live), with the time the source
-- says it was published (or went live) and the time ClipForge detected it,
-- and how (push or poll). (platform, kind, external_id) is unique, so a
-- duplicate notification adds no alert. No foreign keys: alerts outlive
-- their channel, streamer and project.

ALTER TABLE watched_channel ADD COLUMN push_state TEXT NOT NULL DEFAULT 'off';
ALTER TABLE watched_channel ADD COLUMN push_lease_expires_at DATETIME;
ALTER TABLE watched_channel ADD COLUMN push_requested_at DATETIME;
ALTER TABLE watched_channel ADD COLUMN push_error TEXT;

CREATE TABLE watched_streamer (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL UNIQUE,
    user_id TEXT,
    display_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL,
    push_state TEXT NOT NULL,
    push_requested_at DATETIME,
    push_error TEXT,
    subscription_id TEXT,
    live_since DATETIME,
    last_live_at DATETIME,
    last_checked_at DATETIME,
    last_error TEXT,
    created_at DATETIME NOT NULL
);

CREATE TABLE watch_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    kind TEXT NOT NULL,
    external_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    project_id INTEGER,
    published_at DATETIME,
    detected_at DATETIME NOT NULL,
    via TEXT NOT NULL,
    UNIQUE (platform, kind, external_id)
);
