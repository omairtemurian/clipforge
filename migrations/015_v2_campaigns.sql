-- 015_v2_campaigns: clipping campaigns with the evidence that the owner may
-- clip the creator (SPEC-v2 3.18).
--
-- campaign: everything is entered by the owner. The list columns
-- (source_channel_urls, allowed_platforms, required_hashtags,
-- required_tags_mentions) are JSON lists of strings. end_date is a date
-- (YYYY-MM-DD) or NULL for an open-ended campaign: the autopilot safety stop
-- of SPEC-v2 3.19 needs it (docs/decisions.md). The permission evidence is
-- permission_source_url, a screenshot kept as an asset
-- (permission_screenshot_asset_id) and permission_checked_at, which the
-- server sets when the URL or the screenshot is saved.
-- monetization_allowed_elsewhere is NULL while unknown.
--
-- project.campaign_id (added by 005_v2_assets_rights) has no foreign key
-- (SQLite cannot add one to an existing column); deleting a campaign
-- clears it in code. The screenshot asset is deleted with its campaign
-- in code too.

CREATE TABLE campaign (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_screenshot_asset_id INTEGER REFERENCES asset (id) ON DELETE SET NULL,
    permission_checked_at DATETIME,
    name TEXT NOT NULL,
    creator_name TEXT NOT NULL,
    source_channel_urls TEXT NOT NULL,
    platform_board TEXT NOT NULL,
    campaign_url TEXT,
    permission_source_url TEXT,
    badge TEXT NOT NULL,
    rate_per_1k_usd REAL,
    budget_note TEXT NOT NULL,
    allowed_platforms TEXT NOT NULL,
    required_hashtags TEXT NOT NULL,
    required_credit_line TEXT NOT NULL,
    required_tags_mentions TEXT NOT NULL,
    min_duration_s REAL,
    max_duration_s REAL,
    banned_content_notes TEXT NOT NULL,
    monetization_allowed_elsewhere BOOLEAN,
    submission_instructions TEXT NOT NULL,
    status TEXT NOT NULL,
    notes TEXT NOT NULL,
    end_date DATE
);
