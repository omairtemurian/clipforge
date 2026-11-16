-- 022_v2_result_sets: reprompt keeps the old clips (SPEC-v2 3.2, TASK-74).
--
-- A reprompt asks the LLM again with a new prompt and saves the clips it
-- finds as the project's next result set. clip.result_set is the set a clip
-- belongs to; project.result_set is the current one, whose clips the
-- project shows; the lower sets are its previous results. Every existing
-- project and clip is in set 1.

ALTER TABLE project ADD COLUMN result_set INTEGER NOT NULL DEFAULT 1;
ALTER TABLE clip ADD COLUMN result_set INTEGER NOT NULL DEFAULT 1;
