-- 032_v2_archive: archived projects (SPEC-v2 3.11 storage manager, TASK-156).
--
-- archived_at is NULL for a project that is not archived. Archiving deletes a
-- project's source video and work files and keeps its rendered clips, its
-- transcript (search, downloads) and thumbnail; an archived project's clips
-- can no longer be rendered. Existing projects are not archived.

ALTER TABLE project ADD COLUMN archived_at DATETIME;
