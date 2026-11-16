-- 011_settings_panel: the clip settings panel's new options (STEERING item 10, TASK-39).
--
-- auto_color is 1 when the render levels the clip's colours (auto color
-- correction); show_captions is 0 when the clip has no word captions (its
-- hook still shows). Clips made before have neither: 0 and 1.
--
-- A project's settings held one length_preset; they now hold a list,
-- length_presets, of which a clip fits any one.

ALTER TABLE clip ADD COLUMN auto_color BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE clip ADD COLUMN show_captions BOOLEAN NOT NULL DEFAULT 1;

UPDATE project
SET settings = json_remove(
    json_set(
        settings,
        '$.length_presets',
        json_array(json_extract(settings, '$.length_preset'))
    ),
    '$.length_preset'
)
WHERE json_type(settings, '$.length_preset') IS NOT NULL;
