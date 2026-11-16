"""Tests of the library full-text search (SPEC-v2 3.11): what the user types
becomes safe FTS5 queries, projects are indexed when their transcript is made
or changes, hits say the project and the exact second, and a deleted project
leaves no hits."""

from pathlib import Path

import pytest
from builders import said
from clipforge import vocabulary
from clipforge.db import ProjectRow
from clipforge.models import ProcessingSettings, Transcript
from clipforge.pipeline.step import TRANSCRIPT, job_dir, write_json
from clipforge.process import create_job, run_step
from clipforge.search import fts
from clipforge.search.query import SearchQueryError, parse_query, split_highlights
from seed import add_project, add_work
from sqlalchemy import Engine
from sqlmodel import Session


@pytest.fixture
def library(engine: Engine, sample_mp4: Path) -> tuple[int, Path]:
    """A project with the fixture transcript (14 segments), not indexed."""
    project = add_project(engine)
    return project, add_work(engine, project, sample_mp4)


def test_a_query_is_words_never_fts5_syntax() -> None:
    assert parse_query('Smart "my body" fri').match == '"Smart" "my body" "fri"*'
    assert parse_query('"my body"').match == '"my body"'
    assert parse_query("cheese AND NOT -x: (y)").match == (
        '"cheese" "AND" "NOT" "x" "y"*'
    )
    assert parse_query("Café").words == {"cafe"}
    assert parse_query("it's").match == '"it" "s"*'


@pytest.mark.parametrize("text", ["", "   ", '""', "-- ** ::", '" "'])
def test_a_query_without_words_is_refused(text: str) -> None:
    with pytest.raises(SearchQueryError):
        parse_query(text)


def test_highlights_are_where_the_marks_were() -> None:
    text, spans = split_highlights("Last \x02night\x03 the \x02note\x03")

    assert text == "Last night the note"
    assert [(s.start, s.end) for s in spans] == [(5, 10), (15, 19)]
    assert text[5:10] == "night"


def test_a_transcript_is_found_by_its_words_at_the_exact_moment(
    engine: Engine, library: tuple[int, Path]
) -> None:
    project, _ = library

    hits = fts.search(engine, "cheese")

    assert len(hits) == 1
    hit = hits[0]
    assert (hit.project_id, hit.segment_id) == (project, 7)
    assert hit.project_title == "talk"
    assert hit.text == (
        "Last night the notification just said, we should talk about the cheese."
    )
    assert (hit.segment_start, hit.end) == (27.65, 32.85)
    assert 27.65 < hit.start < 32.85
    spoken = {w.text.strip(".,").lower(): w.start for w in words_of(library[1], 7)}
    assert hit.start == spoken["cheese"]
    assert [hit.text[h.start : h.end] for h in hit.highlights] == ["cheese"]


def words_of(work: Path, segment_id: int):  # type: ignore[no-untyped-def]
    transcript = Transcript.model_validate_json((work / TRANSCRIPT).read_text())
    return next(s for s in transcript.segments if s.id == segment_id).words


def test_case_accents_phrases_and_prefixes(
    engine: Engine, library: tuple[int, Path]
) -> None:
    assert [h.segment_id for h in fts.search(engine, "YOGA")] == [1]
    assert [h.segment_id for h in fts.search(engine, "fridg")] == [4]
    assert [h.segment_id for h in fts.search(engine, '"my body"')] == [3]
    assert [h.segment_id for h in fts.search(engine, "body my")] == [3]
    assert fts.search(engine, '"body my"') == []
    assert fts.search(engine, "nothing like this") == []
    hit = fts.search(engine, "listen")[0]
    assert hit.segment_id in (2, 3)


def test_syntax_typed_by_the_user_is_only_text(
    engine: Engine, library: tuple[int, Path]
) -> None:
    for risky in ['"cheese', "cheese OR", "NOT cheese", "a*b", "col:cheese", "x -"]:
        fts.search(engine, risky)
    assert [h.segment_id for h in fts.search(engine, 'the "cheese')] == [7]
    assert [h.segment_id for h in fts.search(engine, "col:cheese")] == []
    assert fts.search(engine, "cheese AND") == []


def test_hits_of_several_projects_say_which_and_can_be_limited(
    engine: Engine, sample_mp4: Path
) -> None:
    first, second = add_project(engine), add_project(engine)
    add_work(engine, first, sample_mp4)
    add_work(engine, second, sample_mp4)
    with Session(engine) as session:
        session.get_one(ProjectRow, second).title = "other"
        session.commit()

    hits = fts.search(engine, "yoga")

    assert sorted((h.project_id, h.project_title) for h in hits) == [
        (first, "talk"),
        (second, "other"),
    ]
    only = fts.search(engine, "yoga", project_id=second)
    assert [h.project_id for h in only] == [second]
    assert len(fts.search(engine, "the", limit=3)) == 3


def test_a_changed_transcript_is_indexed_again_on_the_next_search(
    engine: Engine, library: tuple[int, Path]
) -> None:
    project, work = library
    assert fts.search(engine, "cheese")
    assert fts.sync_index(engine) == 0

    transcript = Transcript.model_validate_json((work / TRANSCRIPT).read_text())
    changed = transcript.model_copy(
        update={
            "segments": [
                s.model_copy(update={"text": s.text.replace("cheese", "brie")})
                for s in transcript.segments
            ]
        }
    )
    write_json(work / TRANSCRIPT, changed)

    assert fts.search(engine, "cheese") == []
    assert [h.project_id for h in fts.search(engine, "brie")] == [project]


def test_a_transcript_that_goes_away_leaves_no_hits(
    engine: Engine, library: tuple[int, Path]
) -> None:
    _, work = library
    assert fts.search(engine, "cheese")

    (work / TRANSCRIPT).unlink()

    assert fts.search(engine, "cheese") == []


def test_an_unreadable_transcript_is_skipped_not_fatal(
    engine: Engine, library: tuple[int, Path], sample_mp4: Path
) -> None:
    broken = add_project(engine)
    add_work(engine, broken, sample_mp4)
    (job_dir_of(engine, broken) / TRANSCRIPT).write_text("{not json")

    assert [h.segment_id for h in fts.search(engine, "cheese")] == [7]


def job_dir_of(engine: Engine, project_id: int) -> Path:
    with engine.connect() as conn:
        (job_id,) = conn.exec_driver_sql(
            f"SELECT max(id) FROM job WHERE project_id = {project_id}"
        ).one()
    return job_dir(job_id)


def test_deleting_a_project_removes_its_hits(
    engine: Engine, library: tuple[int, Path]
) -> None:
    project, _ = library
    assert fts.search(engine, "cheese")

    with Session(engine) as session:
        session.delete(session.get_one(ProjectRow, project))
        session.commit()

    assert fts.search(engine, "cheese") == []


def test_replacing_a_word_everywhere_updates_the_index_at_once(
    engine: Engine, library: tuple[int, Path]
) -> None:
    project, work = library
    fts.index_project(engine, project, work)

    vocabulary.replace_everywhere(engine, project, work, "cheese", "brie")

    with engine.connect() as conn:
        texts = [
            row[0]
            for row in conn.exec_driver_sql(
                "SELECT text FROM search_fts WHERE rowid > 0"
            )
        ]
    assert any("brie" in text for text in texts)
    assert not any("cheese" in text for text in texts)


def test_the_transcribe_step_indexes_the_transcript(
    engine: Engine, sample_mp4: Path
) -> None:
    job_id = create_job(engine, str(sample_mp4), ProcessingSettings())
    work = job_dir(job_id)
    work.mkdir(parents=True)
    (work / TRANSCRIPT).write_text(
        (Path(__file__).parents[1] / "fixtures" / TRANSCRIPT).read_text()
    )

    run_step(engine, "transcribe", job_id)

    with engine.connect() as conn:
        state = conn.exec_driver_sql(
            "SELECT project_id, segment_count FROM search_state"
        ).all()
        found = conn.exec_driver_sql(
            "SELECT count(*) FROM search_fts WHERE search_fts MATCH 'cheese'"
        ).scalar()
    assert [tuple(row) for row in state] == [(1, 14)]
    assert found == 1


def test_a_project_without_segments_text_is_indexed_empty(
    engine: Engine, library: tuple[int, Path]
) -> None:
    project, work = library
    empty = said(("  ", 1.0, 2.0)).model_copy(update={"duration": 60.0})
    write_json(work / TRANSCRIPT, empty)

    assert fts.index_project(engine, project, work) == 0
    assert fts.search(engine, "cheese") == []


def test_fts5_is_available_in_the_bundled_sqlite(engine: Engine) -> None:
    assert fts.fts5_available(engine)
