-- 033_v2_notifications: in-app notifications (SPEC-v2 3.17, TASK-170).
--
-- A notification is a message for the owner: a project is done, a render or
-- post failed, a post was published, a monthly usage cap is nearly used up.
-- read_at is NULL until the owner reads it. dedupe_key (NULL for most) makes
-- a notification that must come once, such as a quota warning of a month,
-- unique. No v1 data changes.

CREATE TABLE notification (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    link TEXT,
    created_at DATETIME NOT NULL,
    read_at DATETIME,
    dedupe_key TEXT UNIQUE
);

CREATE INDEX ix_notification_created_at ON notification (created_at);
