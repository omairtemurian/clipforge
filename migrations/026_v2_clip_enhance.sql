-- 026_v2_clip_enhance: speech enhancement of a clip (SPEC-v2 3.5,
-- pipeline/enhance).
--
-- enhance is how strongly the render cleans the clip's speech, 0 (off) to 1
-- (strongest). v1 clips and clips made before have 0: they render as before.

ALTER TABLE clip ADD COLUMN enhance REAL NOT NULL DEFAULT 0;
