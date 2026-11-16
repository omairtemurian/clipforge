-- 019_v2_post_attempts: when the posting worker last started an upload of
-- a post and when it may try again (SPEC-v2 3.10: rate limits, retries).
--
-- attempted_at is the start of the post's latest upload; the worker counts
-- these per account and per platform for its rate limits. next_attempt_at
-- holds a queued post back until then (retry backoff, a rate limit or a
-- quota waiting to reset); NULL: as soon as it is due. Existing posts have
-- never been uploaded by the worker: both are NULL.

ALTER TABLE post ADD COLUMN attempted_at DATETIME;

ALTER TABLE post ADD COLUMN next_attempt_at DATETIME;
