"""Tests of the music library (SPEC-v2 3.5, api/music): the bundled CC0
loops are in the asset library with their license and attribution, music
uploads are listed after them, both can be filtered by tag and played, and
a music item on a clip's timeline takes fades and ducking as props."""

import shutil
from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from clipforge import assets
from clipforge.ffmpeg import run_ffmpeg
from clipforge.pipeline.music import BUNDLED_TRACKS, MUSIC_DIR
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

TITLES = ["Bright Steps", "Slow Tide", "Night Drive", "Paper Lanterns"]


@pytest.fixture
def song(tmp_path: Path) -> bytes:
    """The bytes of a 1.5 s sine tone as a WAV file."""
    path = tmp_path / "song.wav"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=330:duration=1.5", path])
    return path.read_bytes()


def upload_music(client: TestClient, data: bytes, **form: Any) -> Any:
    """POST /library with data as the music file "My Song.wav"."""
    return client.post(
        "/api/library",
        files={"file": ("My Song.wav", data)},
        data={"kind": "music"} | form,
    )


def test_the_bundled_loops_are_listed_with_license_and_attribution(
    client: TestClient,
) -> None:
    tracks = client.get("/api/music").json()

    assert [track["title"] for track in tracks] == TITLES
    for track, bundled in zip(tracks, BUNDLED_TRACKS, strict=True):
        asset = track["asset"]
        assert track["bundled"] is True
        assert track["tags"] == list(bundled.tags)
        assert asset["kind"] == "music"
        assert asset["license"] == "CC0-1.0"
        assert asset["attribution"] == bundled.attribution
        assert asset["tags"] == ["bundled", *bundled.tags]
        assert Path(asset["path"]) == MUSIC_DIR / bundled.file
        assert track["duration"] > 20


def test_an_uploaded_song_is_listed_after_the_loops_and_filtered_by_tag(
    client: TestClient, song: bytes
) -> None:
    response = upload_music(client, song, license="CC-BY-4.0", tags=["Intro"])

    assert response.status_code == 201
    assert response.json()["asset"]["kind"] == "music"
    assert response.json()["mime"] == "audio/wav"
    tracks = client.get("/api/music").json()
    assert [track["title"] for track in tracks] == [*TITLES, "My Song.wav"]
    upload = tracks[-1]
    assert (upload["bundled"], upload["tags"]) == (False, ["intro"])
    assert upload["duration"] == pytest.approx(1.5, abs=0.05)
    assert upload["asset"]["license"] == "CC-BY-4.0"
    assert [t["title"] for t in client.get("/api/music?tag=Intro").json()] == [
        "My Song.wav"
    ]
    assert [t["title"] for t in client.get("/api/music?tag=calm").json()] == [
        "Slow Tide"
    ]
    library = client.get("/api/library?kind=music").json()
    assert [item["name"] for item in library] == ["My Song.wav"]


def test_a_video_cannot_be_uploaded_as_music(client: TestClient) -> None:
    response = client.post(
        "/api/library",
        files={"file": ("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64)},
        data={"kind": "music"},
    )

    assert response.status_code == 422


def test_music_files_are_served_with_range(client: TestClient, song: bytes) -> None:
    upload_id = upload_music(client, song).json()["asset"]["id"]
    loop_id = client.get("/api/music").json()[0]["asset"]["id"]

    loop = client.get(f"/api/music/{loop_id}/file", headers={"Range": "bytes=0-3"})
    uploaded = client.get(f"/api/music/{upload_id}/file")

    assert loop.status_code == 206
    assert loop.headers["content-type"] == "audio/flac"
    assert loop.content == b"fLaC"
    assert uploaded.status_code == 200
    assert uploaded.headers["content-type"] == "audio/wav"
    assert uploaded.content == song


def test_unknown_or_non_music_assets_have_no_music_file(client: TestClient) -> None:
    font_id = client.get("/api/fonts").json()[0]["asset"]["id"]

    assert_error(client.get("/api/music/9999/file"), 404, "not_found")
    assert_error(client.get(f"/api/music/{font_id}/file"), 404, "not_found")


def test_a_gone_loop_is_left_out(client: TestClient, api_engine: Engine) -> None:
    first = client.get("/api/music").json()[0]["asset"]
    with Session(api_engine) as session:
        assets.update_asset(session, first["id"], path="/nowhere/bright_steps.flac")

    assert [track["title"] for track in client.get("/api/music").json()] == TITLES[1:]
    assert_error(client.get(f"/api/music/{first['id']}/file"), 404, "not_found")


def test_registering_twice_adds_nothing_and_a_move_updates_the_paths(
    api_engine: Engine, tmp_path: Path
) -> None:
    moved = tmp_path / "music"
    moved.mkdir()
    shutil.copy(MUSIC_DIR / BUNDLED_TRACKS[1].file, moved)
    with Session(api_engine) as session:
        assert assets.register_bundled_music(session) == []
        changed = assets.register_bundled_music(session, moved)
        music = assets.list_assets(session, kind="music")

    assert [Path(asset.path) for asset in changed] == [moved / BUNDLED_TRACKS[1].file]
    assert len(music) == len(BUNDLED_TRACKS)


def test_a_music_item_takes_fades_and_ducking_on_a_clips_timeline(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    loop_id = client.get("/api/music").json()[1]["asset"]["id"]
    music = {"id": "m", "kind": "audio", "asset_id": loop_id, "start": 0, "end": 2.5}
    props = {"volume": 0.3, "fade_in": 0.5, "fade_out": 1, "duck": False}

    stored = client.patch(
        f"/api/clips/{clip_id}/tracks", json={"music": [music | {"props": props}]}
    )
    refused = client.patch(
        f"/api/clips/{clip_id}/tracks",
        json={"music": [music | {"props": {"fade_in": 11}}]},
    )

    assert stored.status_code == 200
    assert stored.json()["tracks"]["music"][0]["props"] == props | {"offset": 0.0}
    message = assert_error(refused, 422, "validation_error")
    assert "music item 'm': props fade_in:" in message
