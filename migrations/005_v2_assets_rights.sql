-- 005_v2_assets_rights: the asset library, a project's source rights and
-- the usage records (SPEC-v2 1.6, 2.4, 4).
--
-- asset: a file that clips use (logo, font, music, B-roll...) with its license
-- and attribution. tags is a JSON list of strings. The brand logos, intros
-- and outros that v1 stored in brand_template are registered here as assets;
-- the bundled fonts live in assets/fonts, which SQL cannot list, so
-- clipforge.assets.register_bundled_fonts adds them when the app starts.
--
-- project.source_rights is NULL until the owner sets it: v1 projects
-- migrate with it NULL, which means "rights not set" (a later task blocks
-- publishing then). campaign_id has no foreign key because the campaign
-- table comes with the campaigns task.
--
-- usage_record: one row per measured use of compute or a paid service. A
-- project's records outlive the project, so project_id is set NULL when the
-- project is deleted.

CREATE TABLE asset (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    license TEXT NOT NULL,
    attribution TEXT NOT NULL,
    source_url TEXT,
    tags TEXT NOT NULL
);

CREATE TABLE usage_record (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES project (id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    units REAL NOT NULL,
    cost_usd REAL,
    at DATETIME NOT NULL
);

CREATE INDEX ix_usage_record_project_id ON usage_record (project_id);

CREATE INDEX ix_usage_record_at ON usage_record (at);

ALTER TABLE project ADD COLUMN source_rights TEXT;

ALTER TABLE project ADD COLUMN credit_line TEXT NOT NULL DEFAULT '';

ALTER TABLE project ADD COLUMN campaign_id INTEGER;

INSERT INTO asset (kind, path, license, attribution, source_url, tags)
SELECT 'logo', logo_path, 'user-provided', '', NULL, '["brand"]'
FROM brand_template
WHERE logo_path <> ''
ORDER BY id;

INSERT INTO asset (kind, path, license, attribution, source_url, tags)
SELECT 'video', intro_path, 'user-provided', '', NULL, '["brand","intro"]'
FROM brand_template
WHERE intro_path IS NOT NULL AND intro_path <> ''
ORDER BY id;

INSERT INTO asset (kind, path, license, attribution, source_url, tags)
SELECT 'video', outro_path, 'user-provided', '', NULL, '["brand","outro"]'
FROM brand_template
WHERE outro_path IS NOT NULL AND outro_path <> ''
ORDER BY id;
