-- 006_v2_job_priority: a job's priority (SPEC-v2 2.2).
--
-- The worker pool runs the queued job with the highest priority first and,
-- among equal priorities, the oldest (lowest id). v1 jobs get priority 0, so
-- they keep their v1 order (oldest first). The index covers the claim query
-- (status = 'queued' ORDER BY priority DESC, id).

ALTER TABLE job ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;

CREATE INDEX ix_job_status_priority ON job (status, priority);
