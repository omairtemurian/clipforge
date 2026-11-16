-- 036_v2_autopilot_pause: the global "Pause all autopilot" switch of SPEC-v2
-- 3.19 (TASK-182).
--
-- autopilot_pause has at most one row (id 1): while it is there, no campaign's
-- autopilot makes drafts; paused_at is when the owner paused it. Resuming
-- deletes the row. No v1 data changes.

CREATE TABLE autopilot_pause (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    paused_at DATETIME NOT NULL
);
