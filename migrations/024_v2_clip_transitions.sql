-- 024_v2_clip_transitions: the transitions of a clip's render (SPEC-v2 3.5,
-- pipeline/transitions).
--
-- transitions is JSON (models.ClipTransitions): auto, the transition at
-- every jump cut (null: none), and sections, the transition at each cut
-- from one section to the next in play order (null entries: a hard cut).
-- v1 clips and clips made before have none: they render as before.

ALTER TABLE clip ADD COLUMN transitions TEXT NOT NULL
    DEFAULT '{"auto": null, "sections": []}';
