-- 009_clip_auto_zoom: a clip's punch-in zooms (auto zoom, TASK-23).
--
-- zoom_keyframes is JSON (a list of models.ZoomKeyframe: source time t and
-- scale), the punch-ins that pipeline/auto_zoom chose for the clip;
-- auto_zoom is 1 when the render applies them (the editor's Layout panel
-- toggles it). Clips made before auto zoom existed have none: 0 and [].

ALTER TABLE clip ADD COLUMN auto_zoom BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE clip ADD COLUMN zoom_keyframes TEXT NOT NULL DEFAULT '[]';
