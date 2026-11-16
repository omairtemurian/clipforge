-- 040_proedit_runs: what a Pro Edit run is (SPEC-v3 3.8, 6; TASK-224).
--
-- job_id is the job that runs it (its progress and ETA; NULL once the job
-- is deleted), mode what it does (start: a new variant's first plan;
-- regenerate: a new Director plan; critic: the critic again on the current
-- plan; render: a re-render of the current plan), options the owner's
-- choices as JSON (preset, intensity, style recipe, music, critic on/off;
-- NULL for runs made before) and notes the JSON list of messages the UI
-- shows (why the rule-based Director made the plan, why the critic stopped).
-- Existing runs get mode 'start' and no notes. No v1/v2 data changes.

ALTER TABLE pro_edit_run ADD COLUMN job_id INTEGER
    REFERENCES job (id) ON DELETE SET NULL;
ALTER TABLE pro_edit_run ADD COLUMN mode TEXT NOT NULL DEFAULT 'start';
ALTER TABLE pro_edit_run ADD COLUMN options TEXT;
ALTER TABLE pro_edit_run ADD COLUMN notes TEXT NOT NULL DEFAULT '[]';
CREATE INDEX ix_pro_edit_run_job_id ON pro_edit_run (job_id);
