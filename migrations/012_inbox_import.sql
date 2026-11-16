-- 012_inbox_import: the files that the inbox folder watch has imported (SPEC-v2 3.1).
--
-- One row per imported file, keyed by its absolute path, size in bytes and
-- modification time in nanoseconds: the same file is not imported twice, a
-- file that was changed or replaced under the same name is imported again.
-- project_id has no foreign key: deleting the project must not make the
-- watch import the file again.

CREATE TABLE inbox_import (
    path TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    imported_at DATETIME NOT NULL,
    PRIMARY KEY (path, size, mtime_ns)
);
