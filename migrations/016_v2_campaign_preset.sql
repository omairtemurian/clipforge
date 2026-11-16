-- 016_v2_campaign_preset: the caption template of a campaign's preset
-- (TASK-174, SPEC-v2 3.18).
--
-- Applying a campaign to a project sets the project's caption template (and
-- that of its clips) to this one; NULL keeps theirs. Campaigns made before
-- have none.

ALTER TABLE campaign ADD COLUMN caption_template TEXT;
