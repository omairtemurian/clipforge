-- 034_v2_submissions: the submission tracker and the campaign accounts of
-- SPEC-v2 3.18 (TASK-177).
--
-- campaign_account maps a campaign to the owner's own social accounts; the
-- bulk scheduler of a campaign posts to them. A mapping goes with its
-- campaign or its account.
--
-- submission is the owner's record of submitting one published post on the
-- campaign's board: one row per post, made when the post is first listed
-- (status not_submitted). campaign_id is the campaign of the post's project
-- at that time; it becomes NULL if the campaign is deleted, so that the
-- payouts entered stay. approved_views and payout_usd are entered by the
-- owner. No v1 data changes.

CREATE TABLE campaign_account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL REFERENCES campaign (id) ON DELETE CASCADE,
    account_id INTEGER NOT NULL
        REFERENCES social_account (id) ON DELETE CASCADE,
    UNIQUE (campaign_id, account_id)
);

CREATE INDEX ix_campaign_account_account_id ON campaign_account (account_id);

CREATE TABLE submission (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL UNIQUE REFERENCES post (id) ON DELETE CASCADE,
    campaign_id INTEGER REFERENCES campaign (id) ON DELETE SET NULL,
    submitted_at DATETIME,
    status TEXT NOT NULL,
    approved_views INTEGER,
    payout_usd REAL,
    notes TEXT NOT NULL
);

CREATE INDEX ix_submission_campaign_id ON submission (campaign_id);
