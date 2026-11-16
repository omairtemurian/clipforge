-- 038_v2_submission_answered_at: when the owner last entered the campaign
-- board's answer or numbers (SPEC-v2 3.19 daily digest, TASK-186).
--
-- answered_at is set when a submission becomes approved, rejected or paid, or
-- when its approved views or payout change; it is cleared when the
-- submission goes back to not_submitted or submitted. The digest's "estimated
-- earnings yesterday" sums the approved views entered on that day. Existing
-- submissions get none. No v1 data changes.

ALTER TABLE submission ADD COLUMN answered_at DATETIME;
