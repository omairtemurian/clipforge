-- 039_proedit: the data of Pro Edit (SPEC-v3 6, TASK-201).
--
-- A Pro Edit variant is a clip of its own: clip.parent_clip_id points to the
-- clip it was made from (deleting the original deletes its variants) and
-- clip.variant is 'pro_edit'; every clip that exists keeps variant
-- 'original' and no parent. A plan (pro_edit_plan) is one version of the
-- edit decisions of a clip; its edit decisions are edl_item rows numbered
-- from 1 within the plan (item_id), params as JSON. pro_edit_run is one run
-- of Pro Edit (critic_scores: JSON list of rounds). style_recipe and
-- style_reference are the looks learned from links (features as JSON, never
-- media). The audio columns of asset (bpm, key, ...) are NULL for every asset
-- that exists; license, attribution and source_url are already there. The
-- campaign's heavy-edits switch starts 'unknown' and the autopilot's Pro Edit
-- switch off. No v1/v2 data changes.

ALTER TABLE clip ADD COLUMN parent_clip_id INTEGER
    REFERENCES clip (id) ON DELETE CASCADE;
ALTER TABLE clip ADD COLUMN variant TEXT NOT NULL DEFAULT 'original';
CREATE INDEX ix_clip_parent_clip_id ON clip (parent_clip_id);

CREATE TABLE style_recipe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    features TEXT NOT NULL,
    reference_count INTEGER NOT NULL,
    created_at DATETIME NOT NULL
);

CREATE TABLE style_reference (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL REFERENCES style_recipe (id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    analyzed_at DATETIME,
    deleted_at DATETIME,
    rights_confirmed_at DATETIME NOT NULL
);

CREATE INDEX ix_style_reference_recipe_id ON style_reference (recipe_id);

CREATE TABLE pro_edit_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clip (id) ON DELETE CASCADE,
    preset TEXT NOT NULL,
    intensity TEXT NOT NULL,
    style_recipe_id INTEGER REFERENCES style_recipe (id) ON DELETE SET NULL,
    version INTEGER NOT NULL,
    rationale TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE (clip_id, version)
);

CREATE INDEX ix_pro_edit_plan_clip_id ON pro_edit_plan (clip_id);

CREATE TABLE edl_item (
    plan_id INTEGER NOT NULL REFERENCES pro_edit_plan (id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL,
    t_start FLOAT NOT NULL,
    t_end FLOAT NOT NULL,
    kind TEXT NOT NULL,
    params TEXT NOT NULL,
    reason TEXT NOT NULL,
    source TEXT NOT NULL,
    PRIMARY KEY (plan_id, item_id)
);

CREATE TABLE pro_edit_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clip (id) ON DELETE CASCADE,
    plan_id INTEGER REFERENCES pro_edit_plan (id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    rounds INTEGER NOT NULL,
    critic_scores TEXT NOT NULL,
    cost_estimate FLOAT,
    cost_actual FLOAT,
    started_at DATETIME,
    finished_at DATETIME,
    error TEXT
);

CREATE INDEX ix_pro_edit_run_clip_id ON pro_edit_run (clip_id);
CREATE INDEX ix_pro_edit_run_plan_id ON pro_edit_run (plan_id);

ALTER TABLE asset ADD COLUMN bpm FLOAT;
ALTER TABLE asset ADD COLUMN key TEXT;
ALTER TABLE asset ADD COLUMN loudness_lufs FLOAT;
ALTER TABLE asset ADD COLUMN energy_curve TEXT;
ALTER TABLE asset ADD COLUMN category TEXT;
ALTER TABLE asset ADD COLUMN mood TEXT;
ALTER TABLE asset ADD COLUMN downloaded_at DATETIME;

ALTER TABLE campaign ADD COLUMN allow_heavy_edits TEXT NOT NULL DEFAULT 'unknown';

ALTER TABLE autopilot_settings ADD COLUMN proedit_enabled BOOLEAN NOT NULL DEFAULT 0;
ALTER TABLE autopilot_settings ADD COLUMN proedit_preset TEXT NOT NULL
    DEFAULT 'clean_pro';
ALTER TABLE autopilot_settings ADD COLUMN proedit_max_intensity TEXT NOT NULL
    DEFAULT 'standard';
