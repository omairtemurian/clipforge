-- 030_v2_collections: collections of clips (SPEC-v2 3.11, 3.9, 4: Collection,
-- CollectionItem).
--
-- A collection is a named, ordered set of clips from any projects, which the
-- owner can export as one zip. position orders the items inside a collection
-- (0 is first); a clip is in a collection at most once. Deleting a
-- collection or a clip removes its items. No v1 data changes.

CREATE TABLE collection (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE TABLE collection_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL
        REFERENCES collection (id) ON DELETE CASCADE,
    clip_id INTEGER NOT NULL REFERENCES clip (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    added_at DATETIME NOT NULL,
    UNIQUE (collection_id, clip_id)
);

CREATE INDEX ix_collection_item_clip_id ON collection_item (clip_id);
