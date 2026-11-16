"""The app runs the inbox folder watch when inbox_dir is set: a video put in
the folder shows up as a project, and a stopped app stops watching."""

import time
from pathlib import Path

import pytest
from clipforge import config
from clipforge.api.app import create_app
from fastapi.testclient import TestClient


def _wait_for_projects(client: TestClient, count: int) -> list[dict[str, object]]:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        projects: list[dict[str, object]] = client.get("/api/projects").json()
        if len(projects) >= count:
            return projects
        time.sleep(0.05)
    raise AssertionError(f"fewer than {count} projects after 15 s")


def test_a_video_put_in_the_inbox_becomes_a_project(
    data_dir: Path, tmp_path: Path, sample_mp4: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    cfg = config.settings.model_copy(
        update={"inbox_dir": str(inbox), "inbox_poll_s": 0.05}
    )
    monkeypatch.setattr(config, "settings", cfg)
    app = create_app(run_worker=False, caption_previews=False)

    with TestClient(app) as client:
        assert client.get("/api/projects").json() == []
        (inbox / "episode.mp4").write_bytes(sample_mp4.read_bytes())
        (project,) = _wait_for_projects(client, 1)
        time.sleep(0.3)
        assert len(client.get("/api/projects").json()) == 1

    assert project["status"] == "queued"
    assert str(project["source_path"]) == str(inbox / "episode.mp4")


def test_without_inbox_dir_nothing_is_watched(client: TestClient) -> None:
    assert client.get("/api/projects").json() == []
