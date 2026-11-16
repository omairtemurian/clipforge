-- 023_v2_clip_versions: the versions of a clip, for undo/redo and version
-- restore (SPEC-v2 3.5; ClipVersion, an implementation helper).
--
-- clip_version: one row per saved state of a clip. number grows per clip
-- and is never reused. kind is original (the clip before its first edit),
-- edit or restore (restored_from: the version it copied). fields is a JSON
-- list of the state fields that differ from the version before; state is
-- the JSON models.ClipState. current marks the version the clip shows (one
-- per clip that has versions). Deleting a clip deletes its versions.
--
-- No v1 data changes: a clip's history starts at its next edit, which first
-- stores the clip as it was (its original version).

CREATE TABLE clip_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clip (id) ON DELETE CASCADE,
    number INTEGER NOT NULL,
    kind TEXT NOT NULL,
    restored_from INTEGER,
    fields TEXT NOT NULL,
    state TEXT NOT NULL,
    current BOOLEAN NOT NULL,
    created_at DATETIME NOT NULL,
    UNIQUE (clip_id, number)
);
