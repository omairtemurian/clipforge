"""Full-text search over the transcripts of all projects (SPEC-v2 3.11) with
SQLite FTS5.

The search_fts table (migration 031_v2_search) holds a row for each segment
of each project's transcript.json; search_state says which transcript file
each project's rows come from (its modification time and size). A project is
indexed when its transcribe step finishes and when its transcript is
corrected (index_project); search also indexes first every project whose
transcript is new or changed since (sync_index), so the index follows the
files whatever changed them. Deleting a project removes its rows (a trigger
of the migration).
"""

import logging
from pathlib import Path

from sqlalchemy import Engine, func
from sqlmodel import Session, col, select

from clipforge.db import JobRow
from clipforge.job_rows import process_work_dir
from clipforge.models import SearchHit, Transcript
from clipforge.pipeline.step import TRANSCRIPT, StepError, job_dir, load_json
from clipforge.search.query import (
    MARK_END,
    MARK_START,
    Query,
    moment_time,
    parse_query,
    split_highlights,
)
from clipforge.search.rows import SearchStateRow

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 30

_INSERT = (
    'INSERT INTO search_fts (text, project_id, segment_id, start, "end") '
    "VALUES (?, ?, ?, ?, ?)"
)
_SEARCH = (
    "SELECT search_fts.project_id, project.title, search_fts.segment_id, "
    'search_fts.start, search_fts."end", highlight(search_fts, 0, ?, ?), '
    "search_fts.rank FROM search_fts "
    "JOIN project ON project.id = search_fts.project_id "
    "WHERE search_fts MATCH ?{only} "
    "ORDER BY search_fts.rank, search_fts.project_id, search_fts.start LIMIT ?"
)


def fts5_available(engine: Engine) -> bool:
    """Whether the SQLite that this Python bundles can make FTS5 tables."""
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE VIRTUAL TABLE temp.fts5_probe USING fts5(x)")
            conn.exec_driver_sql("DROP TABLE temp.fts5_probe")
    except Exception:
        return False
    return True


def index_project(engine: Engine, project_id: int, work: Path | None = None) -> int:
    """Index the transcript.json in work (the work directory of the project's
    latest process job if not given) as the project's rows of the search
    index, in place of the earlier ones, and return the segments indexed. A
    project without a transcript has no rows. Raises StepError if the
    transcript is not valid, or if work is not given and the project has no
    process job."""
    with Session(engine) as session:
        if work is None:
            work = process_work_dir(session, project_id)
        path = work / TRANSCRIPT
        if not path.is_file():
            _clear(session, project_id)
            session.commit()
            return 0
        stat = path.stat()
        transcript = load_json(path, Transcript, "transcribe")
        rows = [
            (
                " ".join(segment.text.split()),
                project_id,
                segment.id,
                segment.start,
                segment.end,
            )
            for segment in transcript.segments
            if segment.text.strip()
        ]
        _clear(session, project_id)
        connection = session.connection()
        if rows:
            connection.exec_driver_sql(_INSERT, rows)
        session.add(
            SearchStateRow(
                project_id=project_id,
                transcript_mtime_ns=stat.st_mtime_ns,
                transcript_size=stat.st_size,
                segment_count=len(rows),
            )
        )
        session.commit()
    logger.info("project %d: indexed %d transcript segments", project_id, len(rows))
    return len(rows)


def index_quietly(engine: Engine, project_id: int, work: Path) -> None:
    """index_project, but a failure is only logged: the transcript is then
    indexed by the next search (sync_index) instead of failing the work that
    changed it."""
    try:
        index_project(engine, project_id, work)
    except Exception:
        logger.warning("project %d: transcript not indexed", project_id, exc_info=True)


def sync_index(engine: Engine) -> int:
    """Index every project whose transcript was never indexed or has changed
    since, and drop the rows of one whose transcript is gone; return how many
    projects it changed. A transcript that cannot be read is skipped."""
    with Session(engine) as session:
        latest = session.exec(
            select(JobRow.project_id, func.max(JobRow.id))
            .where(JobRow.kind == "process")
            .group_by(col(JobRow.project_id))
        ).all()
        states = {
            state.project_id: state for state in session.exec(select(SearchStateRow))
        }
    changed = 0
    for project_id, job_id in latest:
        if job_id is None:
            continue
        work = job_dir(job_id)
        path = work / TRANSCRIPT
        state = states.get(project_id)
        if path.is_file():
            stat = path.stat()
            if state is not None and (
                state.transcript_mtime_ns,
                state.transcript_size,
            ) == (
                stat.st_mtime_ns,
                stat.st_size,
            ):
                continue
        elif state is None:
            continue
        try:
            index_project(engine, project_id, work)
        except StepError as exc:
            logger.warning("project %d: not indexed: %s", project_id, exc)
        else:
            changed += 1
    return changed


def search(
    engine: Engine,
    text: str,
    *,
    project_id: int | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchHit]:
    """Return the segments that match text, best first, at most limit, of
    project project_id only if given; the projects' transcripts are indexed
    first (sync_index). Raises SearchQueryError if text has no word."""
    query = parse_query(text)
    sync_index(engine)
    only = "" if project_id is None else " AND search_fts.project_id = ?"
    args: list[object] = [MARK_START, MARK_END, query.match]
    if project_id is not None:
        args.append(project_id)
    args.append(limit)
    with engine.connect() as conn:
        found = conn.exec_driver_sql(_SEARCH.format(only=only), tuple(args)).fetchall()
    transcripts: dict[int, Transcript | None] = {}
    return [_hit(engine, query, transcripts, *row) for row in found]


def _hit(
    engine: Engine,
    query: Query,
    transcripts: dict[int, Transcript | None],
    project_id: int,
    title: str,
    segment_id: int,
    start: float,
    end: float,
    marked: str,
    rank: float,
) -> SearchHit:
    """Return the hit for one row of the search: its text with the matches
    marked, and the moment of the first matching word (from the transcript
    file; the segment's start if that is gone)."""
    if project_id not in transcripts:
        transcripts[project_id] = _transcript(engine, project_id)
    transcript = transcripts[project_id]
    moment = start
    if transcript is not None:
        for segment in transcript.segments:
            if segment.id == segment_id:
                moment = moment_time(segment, query)
                break
    text, highlights = split_highlights(marked)
    return SearchHit(
        project_id=project_id,
        project_title=title,
        segment_id=segment_id,
        start=moment,
        segment_start=start,
        end=end,
        text=text,
        highlights=highlights,
        rank=rank,
    )


def _transcript(engine: Engine, project_id: int) -> Transcript | None:
    """Return the project's transcript, or None if it cannot be read."""
    with Session(engine) as session:
        try:
            return load_json(
                process_work_dir(session, project_id) / TRANSCRIPT,
                Transcript,
                "transcribe",
            )
        except StepError:
            return None


def _clear(session: Session, project_id: int) -> None:
    """Remove the project's rows of the index and its state, in session."""
    session.connection().exec_driver_sql(
        "DELETE FROM search_fts WHERE project_id = ?", (project_id,)
    )
    state = session.get(SearchStateRow, project_id)
    if state is not None:
        session.delete(state)
        session.flush()
