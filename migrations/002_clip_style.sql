-- 002_clip_style: what the editor changes of a clip's look.
--
-- caption_style is JSON: the fields of the caption template that the clip
-- replaces ({} keeps the template). crop_offset shifts the fill window,
-- in fractions of its width.

ALTER TABLE clip ADD COLUMN caption_style TEXT NOT NULL DEFAULT '{}';
ALTER TABLE clip ADD COLUMN crop_offset REAL NOT NULL DEFAULT 0;
