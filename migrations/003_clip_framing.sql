-- 003_clip_framing: how the editor frames a clip on top of its crop plan.
--
-- framing is JSON (models.Framing): the clip's aspect (null: the
-- project's), the fit layout's background, and the crop tool's window
-- scale, points and tracker switch ({} keeps the crop plan as it is).

ALTER TABLE clip ADD COLUMN framing TEXT NOT NULL DEFAULT '{}';
