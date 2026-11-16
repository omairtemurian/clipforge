-- 017_v2_campaign_watch: the creator watch of a campaign (TASK-176, SPEC-v2
-- 3.18).
--
-- watched_channel.campaign_id is the campaign whose source channels
-- registered the channel in Auto Import (NULL: added by the owner). The
-- campaign's channels are removed with it in code, so there is no foreign
-- key (as for project.campaign_id).
--
-- project.source_published_at is when the source video was published, known
-- for the videos that Auto Import found; the "fresh upload" badge of a
-- campaign project is derived from it. NULL for every project before.

ALTER TABLE watched_channel ADD COLUMN campaign_id INTEGER;
ALTER TABLE project ADD COLUMN source_published_at DATETIME;
