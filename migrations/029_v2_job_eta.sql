-- 029_v2_job_eta: overall progress and ETA of a job and its project, and
-- whether the owner opened a finished project (steering, owner request
-- 2026-11-02).
--
-- overall_progress is 0..1 across all steps of the job (job_progress);
-- eta_seconds is NULL while unknown. The project copies both from its running
-- process or reprompt job. opened_at is NULL until the owner opens the project
-- once it is done ("New" badge); projects that exist now count as opened.

ALTER TABLE job ADD COLUMN overall_progress REAL NOT NULL DEFAULT 0.0;
ALTER TABLE job ADD COLUMN eta_seconds REAL;

ALTER TABLE project ADD COLUMN overall_progress REAL NOT NULL DEFAULT 0.0;
ALTER TABLE project ADD COLUMN eta_seconds REAL;
ALTER TABLE project ADD COLUMN opened_at DATETIME;

UPDATE job SET overall_progress = 1.0 WHERE status = 'done';
UPDATE project SET overall_progress = 1.0, opened_at = CURRENT_TIMESTAMP
WHERE status = 'done';
UPDATE project SET opened_at = CURRENT_TIMESTAMP WHERE opened_at IS NULL;
