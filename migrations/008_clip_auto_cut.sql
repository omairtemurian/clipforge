-- 008_clip_auto_cut: whether a clip's silences are cut (auto cut, TASK-27).
--
-- auto_cut is 1 when the clip's cut_ranges hold the auto cut's jump cuts
-- (the editor's Layout panel toggles them). Clips made before auto cut
-- existed have none: 0.

ALTER TABLE clip ADD COLUMN auto_cut BOOLEAN NOT NULL DEFAULT 0;
