-- 007_v2_job_attempts: how many times a job was started (SPEC-v2 2.2).
--
-- The worker counts an attempt each time it claims a job. A job that the
-- app left running when it stopped is queued again and resumes after its
-- last finished step, unless it already had job_max_attempts attempts: such
-- a poison job fails. A v1 job that a worker has claimed (any status but
-- queued) counts one attempt; a queued v1 job none.

ALTER TABLE job ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;

UPDATE job SET attempts = 1 WHERE status != 'queued';
