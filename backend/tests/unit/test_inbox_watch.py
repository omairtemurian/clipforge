"""Tests for the inbox folder watch (clipforge.inbox_watch): stable-size
import, no re-import by path+size+mtime, non-video files, usage caps, the
fake clock, the settings and the app's lifespan."""

import os
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from clipforge import config, usage
from clipforge.config import Settings
from clipforge.db import JobRow, ProjectRow
from clipforge.inbox_watch import InboxWatcher
from fake_clock import FakeClock
from sqlalchemy import Engine
from sqlmodel import Session, select


@pytest.fixture
def inbox(tmp_path: Path) -> Path:
    folder = tmp_path / "inbox"
    folder.mkdir()
    return folder


def _video(folder: Path, name: str = "talk.mp4", data: bytes = b"x" * 100) -> Path:
    path = folder / name
    path.write_bytes(data)
    return path


def _projects(engine: Engine) -> list[ProjectRow]:
    with Session(engine) as session:
        return list(session.exec(select(ProjectRow).order_by(ProjectRow.id)))


def test_a_file_is_imported_when_its_size_is_stable_across_two_polls(
    engine: Engine, inbox: Path
) -> None:
    watcher = InboxWatcher(engine, inbox)
    path = _video(inbox)

    assert watcher.poll() == []
    assert _projects(engine) == []
    assert len(watcher.poll()) == 1

    (project,) = _projects(engine)
    assert project.source_path == str(path)
    assert project.status == "queued"
    with Session(engine) as session:
        jobs = session.exec(select(JobRow)).all()
    assert [(job.kind, job.status, job.project_id) for job in jobs] == [
        ("process", "queued", project.id)
    ]
    assert path.read_bytes() == b"x" * 100


def test_a_file_that_is_still_growing_waits(engine: Engine, inbox: Path) -> None:
    watcher = InboxWatcher(engine, inbox)
    path = _video(inbox, data=b"x" * 10)
    watcher.poll()
    path.write_bytes(b"x" * 20)
    assert watcher.poll() == []
    path.write_bytes(b"x" * 30)
    assert watcher.poll() == []
    assert _projects(engine) == []

    assert len(watcher.poll()) == 1


def test_a_file_with_a_new_mtime_but_the_same_size_waits(
    engine: Engine, inbox: Path
) -> None:
    watcher = InboxWatcher(engine, inbox)
    path = _video(inbox)
    watcher.poll()
    os.utime(path, ns=(1, 1_700_000_000_000_000_000))

    assert watcher.poll() == []
    assert len(watcher.poll()) == 1


def test_an_imported_file_is_not_imported_again(engine: Engine, inbox: Path) -> None:
    watcher = InboxWatcher(engine, inbox)
    _video(inbox)
    watcher.poll()
    watcher.poll()

    for _ in range(3):
        assert watcher.poll() == []
    restarted = InboxWatcher(engine, inbox)
    assert restarted.poll() == [] and restarted.poll() == []
    assert len(_projects(engine)) == 1


def test_a_deleted_project_is_not_imported_again(engine: Engine, inbox: Path) -> None:
    watcher = InboxWatcher(engine, inbox)
    _video(inbox)
    watcher.poll()
    (project_id,) = watcher.poll()
    with Session(engine) as session:
        session.delete(session.get(ProjectRow, project_id))
        session.commit()

    assert watcher.poll() == [] and watcher.poll() == []
    assert _projects(engine) == []


def test_a_changed_or_replaced_file_is_imported_again(
    engine: Engine, inbox: Path
) -> None:
    watcher = InboxWatcher(engine, inbox)
    path = _video(inbox)
    watcher.poll()
    watcher.poll()

    path.write_bytes(b"y" * 250)
    assert watcher.poll() == []
    assert len(watcher.poll()) == 1
    assert len(_projects(engine)) == 2


def test_other_files_hidden_files_and_empty_files_are_ignored(
    engine: Engine, inbox: Path
) -> None:
    watcher = InboxWatcher(engine, inbox)
    _video(inbox, "notes.txt")
    _video(inbox, "cover.jpg")
    _video(inbox, "clip.mp4.part")
    _video(inbox, ".hidden.mp4")
    _video(inbox, "empty.mp4", data=b"")
    (inbox / "folder.mp4").mkdir()
    (inbox / "sub").mkdir()
    _video(inbox / "sub", "nested.mp4")
    _video(inbox, "Upper.MOV")

    for _ in range(3):
        watcher.poll()

    assert [Path(p.source_path).name for p in _projects(engine)] == ["Upper.MOV"]


def test_a_missing_folder_is_fine_until_it_exists(
    engine: Engine, tmp_path: Path
) -> None:
    folder = tmp_path / "later"
    watcher = InboxWatcher(engine, folder)
    assert watcher.poll() == []

    folder.mkdir()
    _video(folder)
    watcher.poll()
    assert len(watcher.poll()) == 1


def test_a_file_that_disappears_is_forgotten(engine: Engine, inbox: Path) -> None:
    watcher = InboxWatcher(engine, inbox)
    path = _video(inbox)
    watcher.poll()
    path.unlink()
    assert watcher.poll() == []

    _video(inbox)
    assert watcher.poll() == []
    assert len(watcher.poll()) == 1


def test_tick_polls_once_per_interval_of_the_clock(engine: Engine, inbox: Path) -> None:
    clock = FakeClock()
    woken: list[bool] = []
    watcher = InboxWatcher(
        engine, inbox, interval=10, clock=clock, on_import=lambda: woken.append(True)
    )
    _video(inbox)

    assert watcher.tick() == []  # the first poll: the file is seen
    clock.now += 9.9
    assert watcher.tick() == []  # too early: not polled
    assert _projects(engine) == [] and woken == []
    clock.now += 0.1
    assert len(watcher.tick()) == 1
    assert woken == [True]
    clock.now += 10
    assert watcher.tick() == [] and woken == [True]


def test_nothing_is_imported_while_a_usage_cap_is_used_up(
    engine: Engine,
    inbox: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capped = config.settings.model_copy(update={"usage_cap_llm_tokens": 100})
    monkeypatch.setattr(config, "settings", capped)
    usage.record(engine, usage.LLM_TOKENS, 500, at=datetime.now(UTC))
    watcher = InboxWatcher(engine, inbox)
    _video(inbox)
    watcher.poll()
    assert watcher.poll() == [] and watcher.poll() == []
    assert _projects(engine) == []

    monkeypatch.setattr(
        config, "settings", capped.model_copy(update={"usage_cap_llm_tokens": 0})
    )
    assert len(watcher.poll()) == 1


def test_from_settings_needs_an_inbox_dir(
    engine: Engine, inbox: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert InboxWatcher.from_settings(engine) is None

    cfg = Settings(inbox_dir=f" {inbox} ", inbox_poll_s=2.5)
    monkeypatch.setattr(config, "settings", cfg)
    watcher = InboxWatcher.from_settings(engine)

    assert watcher is not None
    assert (watcher.folder, watcher.interval) == (inbox, 2.5)


def test_the_thread_imports_a_file_and_stops(engine: Engine, inbox: Path) -> None:
    _video(inbox)
    woken = threading.Event()
    watcher = InboxWatcher(engine, inbox, interval=0.05, on_import=woken.set)

    watcher.start()
    try:
        assert woken.wait(10)
    finally:
        watcher.stop(5)

    assert len(_projects(engine)) == 1
    with pytest.raises(RuntimeError, match="already started"):
        watcher.start()
        watcher.start()
    watcher.stop(5)
