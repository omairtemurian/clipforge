-- 031_v2_search: full-text search over the transcripts of every project
-- (SPEC-v2 3.11, 4: SearchIndex).
--
-- search_fts is an FTS5 table with one row for each transcript segment: its
-- text is searched, the other columns only say where the segment is
-- (UNINDEXED). unicode61 with remove_diacritics 2 makes the search ignore
-- case and accents. search_state records which transcript file (its
-- modification time and size) the index of a project was made from, so a
-- changed transcript is found and indexed again. Deleting a project removes
-- its state (cascade) and its segments (trigger: a virtual table has no
-- foreign keys). No v1 data changes; projects are indexed when they are
-- next searched.

CREATE VIRTUAL TABLE search_fts USING fts5(
    text,
    project_id UNINDEXED,
    segment_id UNINDEXED,
    start UNINDEXED,
    "end" UNINDEXED,
    tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TABLE search_state (
    project_id INTEGER PRIMARY KEY
        REFERENCES project (id) ON DELETE CASCADE,
    transcript_mtime_ns INTEGER NOT NULL,
    transcript_size INTEGER NOT NULL,
    segment_count INTEGER NOT NULL,
    indexed_at DATETIME NOT NULL
);

CREATE TRIGGER search_fts_project_deleted AFTER DELETE ON project
BEGIN
    DELETE FROM search_fts WHERE project_id = old.id;
END;
