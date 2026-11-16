-- 010_clip_scene_reframes: a clip's per-scene framing (STEERING item 7, TASK-54).
--
-- scene_reframes is JSON (a list of models.SceneReframe: start, end, mode,
-- layout, crop_keyframes, scale, track_seed), the scenes of the clip as the
-- editor framed them, in order and covering the clip. Clips made before
-- scenes existed have none: [], the clip's layout and crop plan throughout.

ALTER TABLE clip ADD COLUMN scene_reframes TEXT NOT NULL DEFAULT '[]';
