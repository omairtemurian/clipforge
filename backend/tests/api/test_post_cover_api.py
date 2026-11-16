"""Tests for the covers of a clip's posts (clipforge.thumbnails and its
endpoints): a frame of the rendered video at a time, an uploaded image,
and applying one to all the clip's posts."""

import shutil
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge.ffmpeg import probe_media
from clipforge.pipeline.render import clip_output
from fastapi.testclient import TestClient
from post_api_fakes import accounts, make_drafts
from seed import add_clip, add_project
from social_fakes import set_rights
from sqlalchemy import Engine

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture
def clip_id(api_engine: Engine, sample_mp4: Path) -> int:
    """A rendered clip whose video is the 60 s sample."""
    project_id = add_project(api_engine)
    set_rights(api_engine, project_id, "own")
    clip = add_clip(api_engine, project_id, "rendered", 70, "Pizza night")
    video = clip_output(project_id, clip)
    video.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(sample_mp4, video)
    return clip


def test_frame_preview_is_a_jpeg_of_the_video_at_t(
    client: TestClient, clip_id: int
) -> None:
    response = client.get(f"/api/clips/{clip_id}/frame", params={"t": 2.5})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8\xff")


def test_frame_preview_refuses_a_time_after_the_end(
    client: TestClient, clip_id: int
) -> None:
    late = client.get(f"/api/clips/{clip_id}/frame", params={"t": 600})
    early = client.get(f"/api/clips/{clip_id}/frame", params={"t": -1})

    assert "pick a time before its end" in assert_error(late, 422, "validation_error")
    assert early.status_code == 422


def test_a_clip_that_is_not_rendered_has_no_frames(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    candidate = add_clip(api_engine, project_id, "candidate", 70)

    response = client.get(f"/api/clips/{candidate}/frame", params={"t": 1})

    assert "Render the clip first" in assert_error(response, 409, "conflict")
    assert_error(client.get("/api/clips/99/frame"), 404, "not_found")


def test_picking_a_frame_saves_an_image_asset(
    client: TestClient, clip_id: int, api_engine: Engine
) -> None:
    response = client.post(f"/api/clips/{clip_id}/thumbnail", json={"time_s": 3.25})
    again = client.post(f"/api/clips/{clip_id}/thumbnail", json={"time_s": 3.25})

    assert response.status_code == 201
    asset = response.json()
    assert asset["kind"] == "image" and asset["license"] == "Frame of the clip"
    assert asset["tags"] == ["thumbnail", "frame", f"clip-{clip_id}"]
    assert Path(asset["path"]).name == f"{clip_id}-3250ms.jpg"
    assert probe_media(Path(asset["path"])).duration >= 0
    assert again.json()["id"] == asset["id"]
    image = client.get(f"/api/thumbnails/{asset['id']}")
    assert (
        image.status_code == 200 and image.content == Path(asset["path"]).read_bytes()
    )


@pytest.mark.parametrize(("data", "suffix"), [(JPEG, ".jpg"), (PNG, ".png")])
def test_an_uploaded_jpeg_or_png_becomes_an_asset(
    client: TestClient, clip_id: int, data: bytes, suffix: str
) -> None:
    response = client.post(
        f"/api/clips/{clip_id}/thumbnail/upload",
        content=data,
        headers={"Content-Type": "application/octet-stream"},
    )

    assert response.status_code == 201
    asset = response.json()
    assert asset["license"] == "Uploaded by the owner"
    assert asset["tags"][:2] == ["thumbnail", "upload"]
    assert Path(asset["path"]).suffix == suffix
    assert Path(asset["path"]).read_bytes() == data


def test_other_uploads_are_refused(client: TestClient, clip_id: int) -> None:
    url = f"/api/clips/{clip_id}/thumbnail/upload"
    for data, message in (
        (b"", "empty"),
        (b"GIF89a" + b"\x00" * 20, "JPEG or PNG"),
        (JPEG + b"\x00" * (8 * 1024 * 1024), "over 8 MB"),
    ):
        response = client.post(url, content=data)
        assert message in assert_error(response, 422, "validation_error")


def test_apply_to_all_sets_the_cover_of_draft_and_queued_posts(
    client: TestClient, clip_id: int, api_engine: Engine
) -> None:
    youtube, tiktok = accounts(api_engine, "youtube", "tiktok")
    drafts = make_drafts(
        client, clip_id, [{"account_id": youtube}, {"account_id": tiktok}]
    )
    client.post(f"/api/posts/{drafts[1]['id']}/cancel")
    asset = client.post(f"/api/clips/{clip_id}/thumbnail", json={"time_s": 1}).json()

    response = client.post(
        f"/api/clips/{clip_id}/thumbnail/apply", json={"asset_id": asset["id"]}
    )

    assert response.status_code == 200
    assert [post["id"] for post in response.json()] == [drafts[0]["id"]]
    posts = {p["id"]: p for p in client.get("/api/posts").json()}
    assert posts[drafts[0]["id"]]["thumbnail_asset_id"] == asset["id"]
    assert posts[drafts[1]["id"]]["thumbnail_asset_id"] is None


def test_apply_needs_an_image_asset(client: TestClient, clip_id: int) -> None:
    response = client.post(
        f"/api/clips/{clip_id}/thumbnail/apply", json={"asset_id": 99}
    )

    assert "no image asset 99" in assert_error(response, 422, "validation_error")
    assert_error(
        client.post("/api/clips/99/thumbnail/apply", json={"asset_id": 1}),
        404,
        "not_found",
    )
    assert_error(client.get("/api/thumbnails/99"), 404, "not_found")
