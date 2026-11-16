-- 025_v2_clip_hook: the viral hook of a clip (SPEC-v2 3.5, pipeline/hooks).
--
-- hook is JSON (models.ClipHook): the hook template, its text and how many
-- seconds it shows over the clip's start; NULL: no hook. v1 clips and
-- clips made before have none: they render as before (with their v1
-- hook_text).

ALTER TABLE clip ADD COLUMN hook TEXT DEFAULT NULL;
