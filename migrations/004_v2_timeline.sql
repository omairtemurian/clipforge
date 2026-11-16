-- 004_v2_timeline: a clip's segments and timeline tracks replace its start
-- and end (SPEC-v2 4).
--
-- segments is JSON: the [start, end] sections of the source that the clip
-- plays, in order. tracks is JSON (models.Timeline): the video, broll,
-- overlays, text, music, sfx and voiceover tracks, each a list of items. A v1
-- clip from start to end gets segments [[start, end]] and a video track with
-- one "source" item video-0 from start to end (clipforge/timeline.py builds
-- the same track); its other tracks are empty.
--
-- Times are written with printf('%!.17g'), which keeps every digit of the
-- double: json_array() of a REAL rounds it to 15 digits in some SQLite
-- versions (3.53.1), so 0.30000000000000004 would become 0.3.
--
-- SQLite cannot drop start and end in place, so the table is rebuilt: create
-- the new table, copy the rows, drop the old one, rename the new one and
-- recreate its index (the runner turns foreign keys off while migrating, so
-- dropping clip does not delete its jobs). The AUTOINCREMENT counter of clip
-- is carried over, so the ids of deleted clips stay unused.

CREATE TABLE clip_v2 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project (id) ON DELETE CASCADE,
    segments TEXT NOT NULL,
    tracks TEXT NOT NULL,
    title TEXT NOT NULL,
    hook_text TEXT NOT NULL,
    description TEXT NOT NULL,
    hashtags TEXT NOT NULL,
    emphasis_words TEXT NOT NULL,
    reason TEXT NOT NULL,
    scores TEXT NOT NULL,
    layout TEXT NOT NULL,
    caption_template TEXT NOT NULL,
    caption_overrides TEXT NOT NULL,
    cut_ranges TEXT NOT NULL,
    status TEXT NOT NULL,
    output_path TEXT,
    caption_style TEXT NOT NULL DEFAULT '{}',
    crop_offset REAL NOT NULL DEFAULT 0,
    framing TEXT NOT NULL DEFAULT '{}'
);

INSERT INTO clip_v2 (
    id, project_id, segments, tracks, title, hook_text, description, hashtags,
    emphasis_words, reason, scores, layout, caption_template,
    caption_overrides, cut_ranges, status, output_path, caption_style,
    crop_offset, framing
)
SELECT
    id,
    project_id,
    json_array(json_array(
        json(printf('%!.17g', start)), json(printf('%!.17g', "end"))
    )),
    json_object(
        'video', json_array(json_object(
            'id', 'video-0',
            'kind', 'source',
            'asset_id', NULL,
            'start', json(printf('%!.17g', start)),
            'end', json(printf('%!.17g', "end")),
            'props', json_object()
        )),
        'broll', json_array(),
        'overlays', json_array(),
        'text', json_array(),
        'music', json_array(),
        'sfx', json_array(),
        'voiceover', json_array()
    ),
    title, hook_text, description, hashtags, emphasis_words, reason, scores,
    layout, caption_template, caption_overrides, cut_ranges, status,
    output_path, caption_style, crop_offset, framing
FROM clip;

DELETE FROM sqlite_sequence WHERE name = 'clip_v2';
INSERT INTO sqlite_sequence (name, seq)
SELECT 'clip_v2', seq FROM sqlite_sequence WHERE name = 'clip';

DROP TABLE clip;

ALTER TABLE clip_v2 RENAME TO clip;

CREATE INDEX ix_clip_project_id ON clip (project_id);
