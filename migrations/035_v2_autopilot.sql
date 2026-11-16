-- 035_v2_autopilot: the autopilot of SPEC-v2 3.19 (TASK-180).
--
-- autopilot_settings is one row per campaign that was ever set up (a campaign
-- without one has the defaults: off). slots is the posting rules as JSON and
-- account_ids the owner's accounts as a JSON list; both go with the row.
--
-- draft is a clip that the autopilot made for the owner to approve (one per
-- clip), and feedback_event is what the owner decided about a clip, kept
-- after the clip is deleted (clip_id becomes NULL) so what was learned stays.
-- No v1 data changes.

CREATE TABLE autopilot_settings (
    campaign_id INTEGER PRIMARY KEY
        REFERENCES campaign (id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL,
    max_clips_per_source INTEGER NOT NULL,
    slots TEXT,
    max_posts_per_day INTEGER NOT NULL,
    draft_ttl_days INTEGER NOT NULL,
    account_ids TEXT NOT NULL,
    min_clip_s FLOAT,
    max_clip_s FLOAT,
    caption_template TEXT,
    brand_template_id INTEGER
        REFERENCES brand_template (id) ON DELETE SET NULL
);

CREATE TABLE draft (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL UNIQUE REFERENCES clip (id) ON DELETE CASCADE,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    rule_results TEXT NOT NULL,
    reject_reason TEXT,
    decided_at DATETIME,
    created_at DATETIME NOT NULL
);

CREATE INDEX ix_draft_campaign_id ON draft (campaign_id);
CREATE INDEX ix_draft_status ON draft (status);

CREATE TABLE feedback_event (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER REFERENCES clip (id) ON DELETE SET NULL,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    reason TEXT,
    at DATETIME NOT NULL
);

CREATE INDEX ix_feedback_event_campaign_id ON feedback_event (campaign_id);
