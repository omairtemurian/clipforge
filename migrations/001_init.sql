-- 001_init: the project, clip, job and brand_template tables.
--
-- The runner in backend/clipforge/db.py wraps each migration in a transaction
-- and records it in schema_version, so migration files must not contain
-- BEGIN, COMMIT or ROLLBACK.
--
-- Nested model fields (project.settings; clip.hashtags, emphasis_words,
-- scores, caption_overrides and cut_ranges) are JSON text.
-- AUTOINCREMENT stops SQLite from reusing the ids of deleted rows, so files
-- left in data/work/<job_id>/ or data/output/<project_id>/ never belong to a
-- new row.

CREATE TABLE project (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT,
    source_path TEXT NOT NULL,
    title TEXT NOT NULL,
    duration REAL NOT NULL,
    thumbnail_path TEXT NOT NULL,
    settings TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE TABLE brand_template (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    logo_path TEXT NOT NULL,
    logo_position TEXT NOT NULL,
    logo_opacity REAL NOT NULL,
    font TEXT NOT NULL,
    primary_color TEXT NOT NULL,
    intro_path TEXT,
    outro_path TEXT
);

CREATE TABLE clip (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project (id) ON DELETE CASCADE,
    start REAL NOT NULL,
    "end" REAL NOT NULL,
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
    output_path TEXT
);

CREATE INDEX ix_clip_project_id ON clip (project_id);

CREATE TABLE job (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES project (id) ON DELETE CASCADE,
    clip_id INTEGER REFERENCES clip (id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    step TEXT NOT NULL,
    progress REAL NOT NULL,
    status TEXT NOT NULL,
    error TEXT,
    log_path TEXT NOT NULL
);

CREATE INDEX ix_job_project_id ON job (project_id);

CREATE INDEX ix_job_clip_id ON job (clip_id);
