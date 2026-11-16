"""Storage manager (SPEC-v2 3.11): the disk space each project uses, cleaning
up the files it no longer needs, and archiving it.

A project's files are its uploaded source video (under data/uploads, if it
was uploaded; a link's video lives only in the work directory), the work
directories of its jobs (data/work/<job id>) and its output directory
(data/output/<project id>: rendered clips, exports, cached previews).

Clean up deletes only what the project can do without or makes again: the
16 kHz audio that transcribe and signals read (AUDIO), the face cache of
reframe (FACE_CACHE), the cached previews (made again when the editor asks)
and, once the project is done, the uploaded copy of its video (the work
directory keeps its own converted copy, source.mp4). Its clips can still be
edited and rendered.

Archive keeps the rendered clips, exports, the transcript (search, transcript
downloads), meta.json and thumbnail, and deletes everything else: the source
video, the work files and the uploaded copy. The project is then archived
(Project.archived_at): its clips can no longer be rendered or edited into new
videos.
"""

import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge import config
from clipforge.db import JobRow, ProjectRow
from clipforge.models import ProjectStorage, StorageCleanup, StorageReport
from clipforge.pipeline.face_cache import FACE_CACHE
from clipforge.pipeline.render import project_output
from clipforge.pipeline.step import AUDIO, META, THUMB, TRANSCRIPT, StepError, job_dir
from clipforge.preview import previews_dir
from clipforge.uploads import uploads_dir

# Work files that clean up deletes from each job directory.
CLEANABLE_WORK = (AUDIO, FACE_CACHE)
# Work files that archive keeps in each job directory.
ARCHIVE_KEEPS = (META, THUMB, TRANSCRIPT)
# Project statuses whose files can be cleaned up or archived (not while a
# job may still read or write them).
IDLE = ("done", "failed")


class StorageRefused(Exception):
    """The project's files cannot be changed now; the message says why."""


def dir_size(path: Path) -> int:
    """Return the bytes of the files under path (0 if it does not exist)."""
    if path.is_file():
        return path.stat().st_size
    if not path.is_dir():
        return 0
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def uploaded_copy(project: ProjectRow) -> Path | None:
    """Return the directory of the project's uploaded video, or None if its
    source is a link or a file outside data/uploads."""
    if not project.source_path:
        return None
    path = Path(project.source_path)
    if path.parent.parent != uploads_dir().absolute():
        return None
    return path.parent


def _job_dirs(session: Session, project_id: int) -> list[Path]:
    """Return the work directories of the project's jobs, oldest first."""
    ids = session.exec(
        select(JobRow.id)
        .where(JobRow.project_id == project_id)
        .order_by(col(JobRow.id))
    ).all()
    return [job_dir(job_id) for job_id in ids if job_id is not None]


def _cleanable(project: ProjectRow, work_dirs: list[Path]) -> list[Path]:
    """Return the files and directories that clean up deletes."""
    paths = [work / name for work in work_dirs for name in CLEANABLE_WORK]
    assert project.id is not None
    paths.append(previews_dir(project.id))
    upload = uploaded_copy(project)
    if upload is not None and project.status == "done":
        paths.append(upload)
    return [path for path in paths if path.exists()]


def _usage(project: ProjectRow, work_dirs: list[Path]) -> ProjectStorage:
    """Return what project uses on disk."""
    assert project.id is not None
    upload = uploaded_copy(project)
    return ProjectStorage(
        project_id=project.id,
        title=project.title,
        status=project.status,
        archived_at=project.archived_at,
        source_bytes=0 if upload is None else dir_size(upload),
        work_bytes=sum(dir_size(work) for work in work_dirs),
        output_bytes=dir_size(project_output(project.id)),
        cleanable_bytes=sum(dir_size(path) for path in _cleanable(project, work_dirs)),
    )


def project_storage(engine: Engine, project_id: int) -> ProjectStorage:
    """Return what project project_id uses on disk; StepError if it does not
    exist."""
    with Session(engine) as session:
        project = _project(session, project_id)
        return _usage(project, _job_dirs(session, project_id))


def storage_report(engine: Engine) -> StorageReport:
    """Return every project's disk use, largest first, with their sum and the
    free space of the data directory's disk."""
    with Session(engine) as session:
        projects = session.exec(select(ProjectRow)).all()
        usage = [
            _usage(project, _job_dirs(session, project.id))
            for project in projects
            if project.id is not None
        ]
    usage.sort(key=lambda item: (-item.total_bytes, -item.project_id))
    data_dir = config.settings.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return StorageReport(
        projects=usage,
        total_bytes=sum(item.total_bytes for item in usage),
        free_bytes=shutil.disk_usage(data_dir).free,
        data_dir=str(data_dir.absolute()),
    )


def cleanup_project(engine: Engine, project_id: int) -> StorageCleanup:
    """Delete the project's files that it can do without (see the module
    docstring) and return the bytes freed. Raises StepError if the project
    does not exist and StorageRefused while it is queued or running."""
    with Session(engine) as session:
        project = _idle_project(session, project_id)
        before = _usage(project, work_dirs := _job_dirs(session, project_id))
        for path in _cleanable(project, work_dirs):
            _remove(path)
    after = project_storage(engine, project_id)
    return StorageCleanup(freed_bytes=_freed(before, after), storage=after)


def archive_project(engine: Engine, project_id: int) -> StorageCleanup:
    """Archive the project: delete its source video and work files but its
    transcript, meta.json and thumbnail, keep its output, and mark it
    archived; return the bytes freed. Raises StepError if the project does
    not exist and StorageRefused while it is queued or running."""
    with Session(engine) as session:
        project = _idle_project(session, project_id)
        work_dirs = _job_dirs(session, project_id)
        before = _usage(project, work_dirs)
        for work in work_dirs:
            if work.is_dir():
                for path in work.iterdir():
                    if path.name not in ARCHIVE_KEEPS:
                        _remove(path)
        _remove(previews_dir(project_id))
        upload = uploaded_copy(project)
        if upload is not None:
            _remove(upload)
        if project.archived_at is None:
            project.archived_at = datetime.now(UTC)
            session.add(project)
            session.commit()
    after = project_storage(engine, project_id)
    return StorageCleanup(freed_bytes=_freed(before, after), storage=after)


def require_not_archived(session: Session, project_id: int) -> None:
    """Raise StorageRefused if project project_id is archived."""
    project = session.get(ProjectRow, project_id)
    if project is not None and project.archived_at is not None:
        raise StorageRefused(
            f"project {project_id} is archived: its source video was deleted"
        )


def _project(session: Session, project_id: int) -> ProjectRow:
    project = session.get(ProjectRow, project_id)
    if project is None:
        raise StepError(f"project {project_id} not found")
    return project


def _idle_project(session: Session, project_id: int) -> ProjectRow:
    project = _project(session, project_id)
    if project.status not in IDLE:
        raise StorageRefused(
            f"project {project_id} is {project.status}; try when it is done"
        )
    return project


def _remove(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _freed(before: ProjectStorage, after: ProjectStorage) -> int:
    return max(0, before.total_bytes - after.total_bytes)
