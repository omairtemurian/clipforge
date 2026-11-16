"""The video_encoder setting on the Settings page (STEERING 2026-10-31)."""

from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge import config, encoders
from fastapi.testclient import TestClient

BOTH = ("libx264", "h264_videotoolbox")


def listing(monkeypatch: pytest.MonkeyPatch, names: tuple[str, ...]) -> None:
    """Make ffmpeg list names as its H.264 encoders."""
    monkeypatch.setattr(encoders, "available_encoders", lambda ffmpeg: names)


def test_get_shows_the_encoder_and_the_ones_ffmpeg_has(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing(monkeypatch, BOTH)
    config.settings = config.Settings(data_dir=config.settings.data_dir)

    body = client.get("/api/settings").json()

    assert body["video_encoder"] == "h264_videotoolbox"
    assert body["video_encoders"] == list(BOTH)


def test_put_saves_the_encoder(
    client: TestClient, work_in_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing(monkeypatch, BOTH)

    response = client.put("/api/settings", json={"video_encoder": "libx264"})

    assert response.status_code == 200
    assert response.json()["video_encoder"] == "libx264"
    assert config.settings.video_encoder == "libx264"
    assert config.settings.render_settings().encoder == "libx264"
    env = (work_in_tmp / ".env.local").read_text().splitlines()
    assert 'VIDEO_ENCODER="libx264"' in env


def test_put_refuses_an_encoder_ffmpeg_lacks(
    client: TestClient, work_in_tmp: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listing(monkeypatch, ("libx264",))

    response = client.put("/api/settings", json={"video_encoder": "h264_videotoolbox"})

    assert_error(response, 422, "validation_error")
    assert "has no h264_videotoolbox" in response.text
    assert not (work_in_tmp / ".env.local").exists()
