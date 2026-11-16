"""Tests of the clip version history (SPEC-v2 3.5, clipforge.clip_versions):
every edit stores a version, whichever code makes it; undo, redo and
restore give the clip a version's tracks and segments exactly; a clip keeps
only its latest clip_versions_kept versions."""

import pytest
from builders import track_item
from clipforge import clip_versions, config
from clipforge.clip_versions import ClipVersionRow, HistoryError
from clipforge.db import ClipRow
from clipforge.models import ClipState, Timeline
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session, select


def edit(engine: Engine, clip_id: int, **fields: object) -> None:
    """Set fields of clip clip_id in a session of its own and commit."""
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        for name, value in fields.items():
            setattr(row, name, value)
        session.add(row)
        session.commit()


def state(engine: Engine, clip_id: int) -> ClipState:
    """Return the stored state of clip clip_id."""
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        return clip_versions.clip_state(row)


def numbers(engine: Engine, clip_id: int) -> list[int]:
    """Return the numbers of clip clip_id's versions, oldest first."""
    with Session(engine) as session:
        return [v.number for v in clip_versions.history(session, clip_id).versions]


def move(engine: Engine, clip_id: int, how: str, *args: int) -> None:
    """Undo, redo or restore (how) clip clip_id in a session of its own."""
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        getattr(clip_versions, how)(session, row, *args)


def texts(*ends: float) -> Timeline:
    """Return a timeline whose text track has one item per end second."""
    items = [
        track_item(f"t{i}", "text", 0.0, end, props={"text": "Hi"})
        for i, end in enumerate(ends)
    ]
    return Timeline(text=items)


@pytest.fixture
def clip_id(engine: Engine) -> int:
    """A stored clip 10-12.5 s, never edited."""
    return add_clip(engine, add_project(engine), "candidate", 80)


def test_a_new_clip_has_no_versions(engine: Engine, clip_id: int) -> None:
    with Session(engine) as session:
        history = clip_versions.history(session, clip_id)

    assert (history.current, history.can_undo, history.can_redo) == (0, False, False)
    assert history.versions == []


def test_the_first_edit_stores_the_original_and_the_edit(
    engine: Engine, clip_id: int
) -> None:
    original = state(engine, clip_id)

    edit(engine, clip_id, title="New title", segments=[(10.0, 11.0), (20.0, 21.0)])

    with Session(engine) as session:
        history = clip_versions.history(session, clip_id)
        first = clip_versions.version(session, clip_id, 1)
        second = clip_versions.version(session, clip_id, 2)
    assert (history.current, history.can_undo, history.can_redo) == (2, True, False)
    assert first is not None and second is not None
    assert (first.kind, first.fields, first.state) == ("original", [], original)
    assert second.kind == "edit"
    assert second.fields == ["segments", "title"]
    assert second.state == state(engine, clip_id)
    assert second.state.segments == [(10.0, 11.0), (20.0, 21.0)]


def test_every_edit_stores_a_version(engine: Engine, clip_id: int) -> None:
    edit(engine, clip_id, title="a")
    edit(engine, clip_id, tracks=texts(1.0))
    edit(engine, clip_id, cut_ranges=[(10.5, 11.0)], auto_cut=True)

    with Session(engine) as session:
        versions = clip_versions.history(session, clip_id).versions
    assert [(v.number, v.kind, v.fields) for v in versions] == [
        (1, "original", []),
        (2, "edit", ["title"]),
        (3, "edit", ["tracks"]),
        (4, "edit", ["cut_ranges", "auto_cut"]),
    ]


def test_changes_outside_the_state_or_to_the_same_values_store_none(
    engine: Engine, clip_id: int
) -> None:
    title = state(engine, clip_id).title
    edit(engine, clip_id, status="rendering", output_path="/out/clip.mp4")
    edit(engine, clip_id, title=title)

    assert numbers(engine, clip_id) == []


def test_edits_in_one_session_flushed_twice_store_two_versions(
    engine: Engine, clip_id: int
) -> None:
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        row.title = "one"
        session.add(row)
        session.flush()
        row.title = "two"
        session.add(row)
        session.commit()

    assert numbers(engine, clip_id) == [1, 2, 3]


def test_undo_and_redo_give_back_the_tracks_and_segments_exactly(
    engine: Engine, clip_id: int
) -> None:
    original = state(engine, clip_id)
    edit(engine, clip_id, tracks=texts(1.0), segments=[(10.0, 11.0), (30.0, 31.5)])
    edited = state(engine, clip_id)
    edit(engine, clip_id, tracks=texts(1.0, 2.0))
    latest = state(engine, clip_id)

    move(engine, clip_id, "undo")
    assert state(engine, clip_id) == edited
    move(engine, clip_id, "undo")
    assert state(engine, clip_id) == original
    move(engine, clip_id, "redo")
    assert state(engine, clip_id) == edited
    move(engine, clip_id, "redo")
    assert state(engine, clip_id) == latest

    with Session(engine) as session:
        history = clip_versions.history(session, clip_id)
    assert (history.current, history.can_undo, history.can_redo) == (3, True, False)
    assert numbers(engine, clip_id) == [1, 2, 3]


def test_nothing_to_undo_or_redo_raises(engine: Engine, clip_id: int) -> None:
    with pytest.raises(HistoryError, match="nothing to undo"):
        move(engine, clip_id, "undo")
    edit(engine, clip_id, title="a")
    with pytest.raises(HistoryError, match="nothing to redo"):
        move(engine, clip_id, "redo")
    move(engine, clip_id, "undo")
    with pytest.raises(HistoryError, match="nothing to undo"):
        move(engine, clip_id, "undo")


def test_an_edit_after_undo_drops_the_undone_versions(
    engine: Engine, clip_id: int
) -> None:
    edit(engine, clip_id, title="a")
    edit(engine, clip_id, title="b")
    move(engine, clip_id, "undo")

    edit(engine, clip_id, title="c")

    with Session(engine) as session:
        history = clip_versions.history(session, clip_id)
        latest = clip_versions.version(session, clip_id, 4)
    assert [v.number for v in history.versions] == [1, 2, 4]
    assert (history.current, history.can_redo) == (4, False)
    assert latest is not None and latest.state.title == "c"


def test_restore_gives_the_version_back_exactly_as_a_new_version(
    engine: Engine, clip_id: int
) -> None:
    edit(engine, clip_id, tracks=texts(1.0), segments=[(10.0, 11.0), (40.0, 42.0)])
    wanted = state(engine, clip_id)
    edit(engine, clip_id, tracks=texts(2.0, 2.5), segments=[(5.0, 9.0)])
    edit(engine, clip_id, title="later")

    move(engine, clip_id, "restore", 2)

    assert state(engine, clip_id) == wanted
    with Session(engine) as session:
        history = clip_versions.history(session, clip_id)
    restored = history.versions[-1]
    assert (restored.number, restored.kind, restored.restored_from) == (
        5,
        "restore",
        2,
    )
    assert restored.fields == ["segments", "tracks", "title"]
    assert (history.current, history.can_undo) == (5, True)
    move(engine, clip_id, "undo")
    assert state(engine, clip_id).title == "later"


def test_restoring_the_current_version_stores_nothing(
    engine: Engine, clip_id: int
) -> None:
    edit(engine, clip_id, title="a")

    move(engine, clip_id, "restore", 2)

    assert numbers(engine, clip_id) == [1, 2]


def test_restoring_a_missing_version_raises(engine: Engine, clip_id: int) -> None:
    edit(engine, clip_id, title="a")

    with pytest.raises(LookupError, match="no version 7"):
        move(engine, clip_id, "restore", 7)


def test_a_clip_keeps_its_latest_versions_only(
    engine: Engine, clip_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config.settings, "clip_versions_kept", 3)

    for title in ("a", "b", "c", "d"):
        edit(engine, clip_id, title=title)

    assert numbers(engine, clip_id) == [3, 4, 5]
    move(engine, clip_id, "undo")
    move(engine, clip_id, "undo")
    assert state(engine, clip_id).title == "b"
    with pytest.raises(HistoryError):
        move(engine, clip_id, "undo")


def test_the_default_limit_keeps_a_hundred_versions() -> None:
    assert config.Settings().clip_versions_kept == 100
    with pytest.raises(ValueError, match="greater than or equal to 2"):
        config.Settings(clip_versions_kept=1)


def test_deleting_a_clip_deletes_its_versions(engine: Engine, clip_id: int) -> None:
    edit(engine, clip_id, title="a")

    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        session.delete(row)
        session.commit()
        left = session.exec(select(ClipVersionRow)).all()

    assert left == []
