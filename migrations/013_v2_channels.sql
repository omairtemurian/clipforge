-- 013_v2_channels: the YouTube channels that Auto Import watches and the
-- videos it saw in their feeds (SPEC-v2 3.1; WatchedChannel is an
-- implementation helper named in PRD-v2).
--
-- watched_channel: one row per channel (channel_id is the "UC..." id of
-- its RSS feed) with the defaults of the projects of its new videos:
-- settings (ProcessingSettings JSON), source_rights, credit_line and the
-- auto_schedule_drafts flag. last_checked_at is the time of the last feed
-- read that worked: NULL means never, and the first read that works only
-- records the videos already in the feed. last_error is the error of the
-- latest read that failed (NULL once a read works).
--
-- watched_video: one row per (channel, video id) seen, so a video makes a
-- project once. project_id has no foreign key: deleting the project must
-- not make the watch import the video again; it is NULL for the videos
-- that were in the feed when the channel was added. Removing a channel
-- removes its rows.

CREATE TABLE watched_channel (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    settings TEXT NOT NULL,
    source_rights TEXT,
    credit_line TEXT NOT NULL,
    auto_schedule_drafts BOOLEAN NOT NULL,
    enabled BOOLEAN NOT NULL,
    last_checked_at DATETIME,
    last_error TEXT,
    created_at DATETIME NOT NULL
);

CREATE TABLE watched_video (
    watched_channel_id INTEGER NOT NULL
        REFERENCES watched_channel (id) ON DELETE CASCADE,
    video_id TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at DATETIME,
    project_id INTEGER,
    seen_at DATETIME NOT NULL,
    PRIMARY KEY (watched_channel_id, video_id)
);
