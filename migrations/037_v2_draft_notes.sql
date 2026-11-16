-- 037_v2_draft_notes: review notes of the autopilot's drafts (SPEC-v2 3.19
-- human-only approval, TASK-183).
--
-- notes is the JSON list of a draft's review notes ({text, by, at}, oldest
-- first): agents (API key, MCP) and the owner may add them, while approving
-- and rejecting stay the owner's. Existing drafts get no notes. No v1 data
-- changes.

ALTER TABLE draft ADD COLUMN notes TEXT NOT NULL DEFAULT '[]';
