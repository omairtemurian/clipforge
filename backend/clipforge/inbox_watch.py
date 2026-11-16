"""The inbox folder watch (SPEC-v2 3.1): a video file that lands in the
configured inbox_dir becomes a project with default settings.

InboxWatcher polls the folder (not its subfolders) every inbox_poll_s. A file
is imported when its size and modification time are the same in two polls in
a row, so a file that is still being copied is left alone. An imported file
is recorded by path, size and modification time (inbox_import table), so it
is not imported again; the file itself is never moved or deleted (ingest
copies it). Hidden files, empty files and files that are not videos are
ignored. While a monthly usage cap is used up nothing is imported: the
files wait and are imported by the first poll after the cap allows it.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Field, Session, SQLModel

from clipforge import config, usage
from clipforge.db import JobRow
from clipforge.jobs import enqueue_process
from clipforge.models import ProcessingSettings
from clipforge.poller import Poller

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".m4v",
        ".mov",
        ".mkv",
        ".webm",
        ".avi",
        ".mpg",
        ".mpeg",
        ".mts",
        ".m2ts",
        ".wmv",
        ".flv",
    }
)

# A file's size in bytes and modification time in nanoseconds.
Signature = tuple[int, int]


class InboxImportRow(SQLModel, table=True):
    """A row of the inbox_import table (migration 012_inbox_import)."""

    __tablename__ = "inbox_import"

    path: str = Field(primary_key=True)
    size: int = Field(primary_key=True)
    mtime_ns: int = Field(primary_key=True)
    project_id: int
    imported_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InboxWatcher(Poller):
    """Imports the new video files of one folder as projects.

    poll() looks at the folder once; tick(), start() and stop() come from
    Poller. on_import is called after a poll that queued projects (the app
    wakes the worker with it).
    """

    thread_name = "clipforge-inbox"

    def __init__(
        self,
        engine: Engine,
        folder: Path,
        *,
        interval: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
        on_import: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(interval=interval, clock=clock)
        self.engine = engine
        self.folder = folder
        self.on_import = on_import
        self._seen: dict[Path, Signature] = {}

    @classmethod
    def from_settings(
        cls, engine: Engine, on_import: Callable[[], None] | None = None
    ) -> "InboxWatcher | None":
        """Return the watcher that the settings ask for (inbox_dir,
        inbox_poll_s), or None if inbox_dir is empty."""
        cfg = config.settings
        if not cfg.inbox_dir.strip():
            return None
        folder = Path(cfg.inbox_dir.strip()).expanduser().absolute()
        return cls(engine, folder, interval=cfg.inbox_poll_s, on_import=on_import)

    def poll(self) -> list[int]:
        """Look at the folder once and return the ids of the projects that it
        queued: the files whose size and modification time are those of the
        previous poll and that were not imported before."""
        current = self._scan()
        imported: list[int] = []
        for path, signature in current.items():
            if self._seen.get(path) != signature or self._was_imported(path, signature):
                continue
            try:
                imported.append(self._import(path, signature))
            except usage.UsageCapExceeded as exc:
                logger.warning("inbox: not importing %s yet: %s", path.name, exc)
                break
            except Exception:
                logger.exception("inbox: importing %s failed", path)
        self._seen = current
        if imported and self.on_import is not None:
            self.on_import()
        return imported

    def _scan(self) -> dict[Path, Signature]:
        """Return the signature of every non-empty video file of the folder
        (none if the folder does not exist)."""
        found: dict[Path, Signature] = {}
        if not self.folder.is_dir():
            return found
        for path in sorted(self.folder.iterdir()):
            if path.name.startswith(".") or path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            try:
                info = path.stat()
            except OSError:
                continue
            if path.is_file() and info.st_size > 0:
                found[path] = (info.st_size, info.st_mtime_ns)
        return found

    def _was_imported(self, path: Path, signature: Signature) -> bool:
        with Session(self.engine) as session:
            return session.get(InboxImportRow, (str(path), *signature)) is not None

    def _import(self, path: Path, signature: Signature) -> int:
        """Queue a project for path, record it as imported and return the
        project id."""
        usage.check_caps(self.engine)
        job_id = enqueue_process(self.engine, str(path), ProcessingSettings())
        with Session(self.engine) as session:
            job = session.get(JobRow, job_id)
            assert job is not None
            session.add(
                InboxImportRow(
                    path=str(path),
                    size=signature[0],
                    mtime_ns=signature[1],
                    project_id=job.project_id,
                )
            )
            session.commit()
            logger.info("inbox: imported %s as project %d", path.name, job.project_id)
            return job.project_id
