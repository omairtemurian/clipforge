"""Tests of PUT and PATCH /clips/{id}/tracks (SPEC-v2 3.5, api/timeline):
valid tracks are stored with their props' defaults, invalid ones (times
outside the clip, unknown kinds, missing assets, bad props) are refused
with 422 and change nothing, and the video track stays the segments'."""

from pathlib import Path
from typing import Any

from apihelpers import assert_error
from clipforge.assets import add_asset
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

VIDEO_TRACK = [
    {
        "id": "video-0",
        "kind": "source",
        "asset_id": None,
        "start": 10.0,
        "end": 12.5,
        "props": {},
    }
]


def music_asset(engine: Engine, tmp_path: Path) -> int:
    """Add a music asset with a file and return its id."""
    path = tmp_path / "song.mp3"
    path.write_bytes(b"x")
    with Session(engine) as session:
        return add_asset(session, "music", str(path), "CC0-1.0").id


def text(item_id: str, start: float, end: float, **props: Any) -> dict[str, Any]:
    """Return a text item that draws "Hi"."""
    return {
        "id": item_id,
        "kind": "text",
        "start": start,
        "end": end,
        "props": {"text": "Hi"} | props,
    }


def test_put_stores_every_track_with_default_props(
    client: TestClient, api_engine: Engine, tmp_path: Path
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    music = music_asset(api_engine, tmp_path)
    sound = {"id": "m", "kind": "audio", "asset_id": music, "start": 0, "end": 2.5}

    response = client.put(
        f"/api/clips/{clip_id}/tracks",
        json={"video": VIDEO_TRACK, "text": [text("t", 0, 1)], "music": [sound]},
    )

    assert response.status_code == 200
    tracks = response.json()["tracks"]
    assert tracks["video"] == VIDEO_TRACK
    assert tracks["text"][0]["props"] == {
        "text": "Hi",
        "font": "Montserrat ExtraBold",
        "size": 0.06,
        "color": "#FFFFFF",
        "stroke": None,
        "stroke_width": 0.08,
        "box": None,
        "box_opacity": 1.0,
        "x": 0.5,
        "y": 0.2,
        "animation_in": "none",
        "animation_out": "none",
        "in_seconds": 0.4,
        "out_seconds": 0.4,
    }
    assert tracks["music"][0]["props"] == {
        "volume": 1.0,
        "offset": 0.0,
        "fade_in": 0.0,
        "fade_out": 0.0,
        "duck": True,
    }
    assert client.get(f"/api/clips/{clip_id}").json()["tracks"] == tracks


def test_put_with_an_empty_video_track_keeps_it_and_clears_the_rest(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    client.put(f"/api/clips/{clip_id}/tracks", json={"text": [text("t", 0, 1)]})

    response = client.put(f"/api/clips/{clip_id}/tracks", json={})

    assert response.status_code == 200
    assert response.json()["tracks"]["video"] == VIDEO_TRACK
    assert response.json()["tracks"]["text"] == []


def test_patch_replaces_only_the_tracks_it_sets(
    client: TestClient, api_engine: Engine, tmp_path: Path
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    music = music_asset(api_engine, tmp_path)
    client.patch(f"/api/clips/{clip_id}/tracks", json={"text": [text("t", 0, 1)]})
    sfx = {"id": "s", "kind": "audio", "asset_id": music, "start": 1, "end": 1.5}

    response = client.patch(f"/api/clips/{clip_id}/tracks", json={"sfx": [sfx]})

    assert response.status_code == 200
    tracks = response.json()["tracks"]
    assert [item["id"] for item in tracks["text"]] == ["t"]
    assert [item["id"] for item in tracks["sfx"]] == ["s"]


def test_invalid_items_are_refused_and_nothing_changes(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    broll = {"id": "b", "kind": "image", "asset_id": 404, "start": 0, "end": 1}

    response = client.patch(
        f"/api/clips/{clip_id}/tracks",
        json={"text": [text("t", 2, 3)], "broll": [broll]},
    )

    message = assert_error(response, 422, "validation_error")
    assert (
        "text item 't': [2, 3] s is not inside the clip, which lasts 2.5 s" in message
    )
    assert "broll item 'b': asset 404 does not exist" in message
    assert client.get(f"/api/clips/{clip_id}").json()["tracks"]["text"] == []


def test_five_text_layers_are_stored_and_a_sixth_is_422(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    url = f"/api/clips/{clip_id}/tracks"
    five = [
        text(f"t{n}", 0.4 * n, 0.4 * n + 0.3, animation_in="fade", box="#000000")
        for n in range(5)
    ]

    stored = client.patch(url, json={"text": five})
    sixth = client.patch(url, json={"text": [*five, text("t5", 2, 2.4)]})

    assert stored.status_code == 200
    assert len(stored.json()["tracks"]["text"]) == 5
    message = assert_error(sixth, 422, "validation_error")
    assert message == "text track: 6 text overlays, at most 5 allowed"
    assert (
        client.get(f"/api/clips/{clip_id}").json()["tracks"] == stored.json()["tracks"]
    )


def test_unknown_kinds_tracks_and_reversed_times_are_422(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    url = f"/api/clips/{clip_id}/tracks"

    sticker = text("t", 0, 1) | {"kind": "sticker"}
    assert_error(client.patch(url, json={"text": [sticker]}), 422, "validation_error")
    assert_error(client.patch(url, json={"video": []}), 422, "validation_error")
    assert_error(
        client.patch(url, json={"text": [text("t", 1, 0.5)]}), 422, "validation_error"
    )


def test_the_video_track_cannot_be_changed_here(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    moved = [VIDEO_TRACK[0] | {"start": 5.0}]

    response = client.put(f"/api/clips/{clip_id}/tracks", json={"video": moved})

    assert "follows the clip's segments" in assert_error(
        response, 422, "validation_error"
    )


def test_missing_and_rendering_clips(client: TestClient, api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "rendering", 80)

    assert_error(client.put("/api/clips/999/tracks", json={}), 404, "not_found")
    assert_error(client.patch(f"/api/clips/{clip_id}/tracks", json={}), 409, "conflict")
