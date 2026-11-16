"""The media library (TASK-104, SPEC-v2 3.5): uploads are sniffed and read by
ffprobe, get a thumbnail, are listed, tagged and deleted (409 while a clip
plays them)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from clipforge import assets, media_library
from clipforge.ffmpeg import run_ffmpeg
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

Make = Callable[[str, list[str]], bytes]


@pytest.fixture
def make(tmp_path: Path) -> Make:
    """A function that has ffmpeg make a file with the given lavfi input
    (and output arguments) and returns its bytes."""
    count = 0

    def run(name: str, args: list[str]) -> bytes:
        nonlocal count
        count += 1
        path = tmp_path / f"made{count}-{name}"
        run_ffmpeg([*args, path])
        return path.read_bytes()

    return run


def color(spec: str = "red") -> list[str]:
    """Input arguments of a 64x48 picture of the color."""
    return ["-f", "lavfi", "-i", f"color=c={spec}:s=64x48:d=1"]


def tone(freq: int = 440) -> list[str]:
    """Input arguments of a 1 s sine tone."""
    return ["-f", "lavfi", "-i", f"sine=frequency={freq}:duration=1"]


def upload(client: TestClient, data: bytes, name: str, **form: Any) -> Any:
    """POST /library with data as the file called name."""
    return client.post("/api/library", files={"file": (name, data)}, data=form)


def test_an_image_is_stored_with_a_png_thumbnail(
    client: TestClient, data_dir: Path, make: Make
) -> None:
    png = make("a.png", [*color(), "-frames:v", "1"])

    response = upload(
        client, png, "../../My Logo.png", license="CC0", attribution="me", tags=["Blue"]
    )

    assert response.status_code == 201
    body = response.json()
    assert (body["name"], body["mime"]) == ("My Logo.png", "image/png")
    assert (body["width"], body["height"], body["duration"]) == (64, 48, None)
    assert body["tags"] == ["blue"] and body["used_in_clips"] == []
    assert body["size_bytes"] == len(png) and body["has_thumbnail"] is True
    asset = body["asset"]
    assert (asset["kind"], asset["license"], asset["attribution"]) == (
        "image",
        "CC0",
        "me",
    )
    path = Path(asset["path"])
    assert path.parent.parent == data_dir / "media" and path.name == "file.png"
    assert path.read_bytes() == png
    thumb = client.get(f"/api/library/{asset['id']}/thumbnail")
    assert thumb.headers["content-type"] == "image/png"
    assert thumb.content.startswith(b"\x89PNG")


def test_a_jpeg_webp_and_gif_are_images_and_a_logo_is_asked_for(
    client: TestClient, make: Make
) -> None:
    files = {
        "a.jpg": ("image/jpeg", [*color("blue"), "-frames:v", "1"]),
        "b.webp": ("image/webp", [*color("green"), "-frames:v", "1"]),
        "c.gif": ("image/gif", color("yellow")),
    }
    for name, (mime, args) in files.items():
        response = upload(client, make(name, args), name, kind="logo")

        assert response.status_code == 201, name
        assert response.json()["mime"] == mime
        assert response.json()["asset"]["kind"] == "logo"
    listed = client.get("/api/library", params={"kind": "logo"}).json()
    assert [i["name"] for i in listed] == ["a.jpg", "b.webp", "c.gif"]


def test_a_video_has_a_frame_thumbnail_and_the_size_and_length(
    client: TestClient, make: Make
) -> None:
    mp4 = make("v.mp4", [*color("orange"), "-pix_fmt", "yuv420p"])

    response = upload(client, mp4, "clip.mov")

    body = response.json()
    assert response.status_code == 201
    assert (body["asset"]["kind"], body["mime"]) == ("video", "video/mp4")
    assert (body["width"], body["height"]) == (64, 48)
    assert body["duration"] == pytest.approx(1.0, abs=0.1)
    thumb = client.get(f"/api/library/{body['asset']['id']}/thumbnail")
    assert thumb.headers["content-type"] == "image/jpeg"
    assert thumb.content.startswith(b"\xff\xd8\xff")


@pytest.mark.parametrize(
    ("name", "args", "mime"),
    [
        ("a.mp3", [*tone(), "-c:a", "libmp3lame"], "audio/mpeg"),
        ("a.wav", tone(), "audio/wav"),
        ("a.m4a", [*tone(), "-c:a", "aac"], "audio/mp4"),
        ("a.ogg", [*tone(), "-c:a", "libvorbis"], "audio/ogg"),
        ("a.flac", tone(), "audio/flac"),
    ],
)
def test_audio_formats_are_sniffed_and_get_a_waveform(
    client: TestClient, make: Make, name: str, args: list[str], mime: str
) -> None:
    response = upload(client, make(name, args), "renamed.bin")

    assert response.status_code == 201
    body = response.json()
    assert (body["asset"]["kind"], body["mime"]) == ("audio", mime)
    assert body["duration"] == pytest.approx(1.0, abs=0.1)
    assert (body["width"], body["height"]) == (None, None)
    thumb = client.get(f"/api/library/{body['asset']['id']}/thumbnail")
    assert thumb.content.startswith(b"\x89PNG")


def test_a_video_file_without_picture_is_audio_and_a_cover_does_not_make_video(
    client: TestClient, make: Make
) -> None:
    mp4_audio = make("a.mp4", [*tone(), "-c:a", "aac"])

    response = upload(client, mp4_audio, "song.mp4")

    assert response.json()["asset"]["kind"] == "audio"


def test_the_kind_must_fit_the_file(client: TestClient, make: Make) -> None:
    png = make("a.png", [*color(), "-frames:v", "1"])
    wav = make("a.wav", tone())

    assert_error(upload(client, png, "a.png", kind="video"), 422, "validation_error")
    assert_error(upload(client, wav, "a.wav", kind="logo"), 422, "validation_error")
    assert_error(upload(client, wav, "a.wav", kind="font"), 422, "validation_error")
    assert client.get("/api/library").json() == []


@pytest.mark.parametrize(
    "data",
    [b"", b"just some text, not media", b"\x89PNG\r\n\x1a\nbroken"],
    ids=["empty", "text", "truncated png"],
)
def test_a_file_that_is_not_media_is_refused_and_nothing_is_stored(
    client: TestClient, data_dir: Path, data: bytes
) -> None:
    response = upload(client, data, "photo.png")

    assert_error(response, 422, "validation_error")
    assert client.get("/api/library").json() == []
    assert not list((data_dir / "media").iterdir())


def test_a_container_with_a_wrong_name_is_judged_by_its_bytes(
    client: TestClient, make: Make
) -> None:
    mp3 = make("a.mp3", [*tone(), "-c:a", "libmp3lame"])

    response = upload(client, mp3, "picture.png")

    assert response.status_code == 201
    assert response.json()["mime"] == "audio/mpeg"


def test_a_truncated_video_is_refused(client: TestClient, make: Make) -> None:
    mp4 = make("v.mp4", [*color(), "-pix_fmt", "yuv420p"])

    assert_error(upload(client, mp4[:60], "v.mp4"), 422, "validation_error")


@pytest.mark.parametrize("limit", [100, 5000], ids=["by its probe", "while copying"])
def test_a_file_over_its_size_limit_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, make: Make, limit: int
) -> None:
    monkeypatch.setitem(media_library.MAX_BYTES, "image", limit)
    big = ["-f", "lavfi", "-i", "testsrc2=s=640x480:d=1", "-frames:v", "1"]
    png = make("a.png", big)
    assert 4096 < len(png)

    response = upload(client, png, "a.png")

    assert_error(response, 422, "validation_error")
    assert f"{limit} bytes" in response.json()["message"]


def test_the_same_file_twice_is_a_conflict(client: TestClient, make: Make) -> None:
    png = make("a.png", [*color(), "-frames:v", "1"])
    upload(client, png, "a.png")

    assert_error(upload(client, png, "b.png"), 409, "conflict")
    assert len(client.get("/api/library").json()) == 1


def test_tags_are_tidied_and_checked(client: TestClient, make: Make) -> None:
    png = make("a.png", [*color(), "-frames:v", "1"])

    bad = upload(client, png, "a.png", tags=["ok", "media-library"])
    assert_error(bad, 422, "validation_error")
    ok = upload(client, png, "a.png", tags=[" Big  Red ", "big red", "", "b-roll"])
    assert ok.json()["tags"] == ["big red", "b-roll"]
    assert upload(client, png, "a.png").status_code == 409


def test_list_filters_by_kind_and_tag_and_leaves_out_other_assets(
    client: TestClient, api_engine: Engine, make: Make
) -> None:
    png = make("a.png", [*color(), "-frames:v", "1"])
    wav = make("a.wav", tone())
    upload(client, png, "a.png", tags=["Hero"])
    upload(client, wav, "a.wav", tags=["hero", "music"])
    with Session(api_engine) as session:
        assets.add_asset(session, "image", "/elsewhere/cover.jpg", "own")

    assert [i["name"] for i in client.get("/api/library").json()] == ["a.png", "a.wav"]
    by_kind = client.get("/api/library", params={"kind": "audio"}).json()
    assert [i["name"] for i in by_kind] == ["a.wav"]
    by_tag = client.get("/api/library", params={"tag": "HERO"}).json()
    assert [i["name"] for i in by_tag] == ["a.png", "a.wav"]
    assert client.get("/api/library", params={"tag": "music"}).json()[0]["name"] == (
        "a.wav"
    )
    assert client.get("/api/library", params={"tag": "nothing"}).json() == []


def test_tags_license_and_attribution_can_be_changed(
    client: TestClient, make: Make
) -> None:
    png = make("a.png", [*color(), "-frames:v", "1"])
    asset_id = upload(client, png, "a.png", tags=["old"]).json()["asset"]["id"]

    response = client.patch(
        f"/api/library/{asset_id}",
        json={"tags": ["New", "Other", "new"], "attribution": "Me"},
    )

    body = response.json()
    assert response.status_code == 200
    assert body["tags"] == ["new", "other"]
    assert (body["asset"]["attribution"], body["asset"]["license"]) == (
        "Me",
        "user-supplied",
    )
    assert "media-library" in body["asset"]["tags"]
    only_license = client.patch(f"/api/library/{asset_id}", json={"license": "CC0"})
    assert only_license.json()["tags"] == ["new", "other"]
    assert_error(
        client.patch(f"/api/library/{asset_id}", json={"tags": ["uploaded"]}),
        422,
        "validation_error",
    )
    assert_error(client.patch("/api/library/999", json={"tags": []}), 404, "not_found")


def test_the_file_is_served_with_ranges(client: TestClient, make: Make) -> None:
    mp4 = make("v.mp4", [*color(), "-pix_fmt", "yuv420p"])
    asset_id = upload(client, mp4, "v.mp4").json()["asset"]["id"]

    full = client.get(f"/api/library/{asset_id}/file")
    part = client.get(f"/api/library/{asset_id}/file", headers={"Range": "bytes=0-99"})

    assert full.headers["content-type"] == "video/mp4" and full.content == mp4
    assert part.status_code == 206 and part.content == mp4[:100]
    assert_error(client.get("/api/library/999/file"), 404, "not_found")
    assert_error(client.get("/api/library/999/thumbnail"), 404, "not_found")


def test_delete_removes_the_asset_and_its_files(client: TestClient, make: Make) -> None:
    png = make("a.png", [*color(), "-frames:v", "1"])
    asset = upload(client, png, "a.png").json()["asset"]
    directory = Path(asset["path"]).parent

    response = client.delete(f"/api/library/{asset['id']}")

    assert response.status_code == 204
    assert not directory.exists()
    assert client.get("/api/library").json() == []
    assert_error(client.delete(f"/api/library/{asset['id']}"), 404, "not_found")
    assert upload(client, png, "a.png").status_code == 201


def test_delete_is_a_conflict_while_a_clip_plays_the_file(
    client: TestClient, api_engine: Engine, make: Make
) -> None:
    mp4 = make("v.mp4", [*color(), "-pix_fmt", "yuv420p"])
    asset = upload(client, mp4, "v.mp4").json()["asset"]
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    item = {"id": "b1", "kind": "video", "asset_id": asset["id"], "start": 0, "end": 1}
    placed = client.patch(f"/api/clips/{clip_id}/tracks", json={"broll": [item]})

    listed = client.get("/api/library").json()
    response = client.delete(f"/api/library/{asset['id']}")

    assert placed.status_code == 200
    assert listed[0]["used_in_clips"] == [clip_id]
    assert_error(response, 409, "conflict")
    assert str(clip_id) in response.json()["message"]
    assert Path(asset["path"]).is_file()
    client.patch(f"/api/clips/{clip_id}/tracks", json={"broll": []})
    assert client.delete(f"/api/library/{asset['id']}").status_code == 204


def test_a_library_image_is_a_timeline_overlay_and_a_logo_too(
    client: TestClient, api_engine: Engine, make: Make
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    png = make("a.png", [*color(), "-frames:v", "1"])
    jpg = make("a.jpg", [*color("blue"), "-frames:v", "1"])
    image = upload(client, png, "a.png").json()["asset"]["id"]
    logo = upload(client, jpg, "a.jpg", kind="logo").json()["asset"]["id"]
    items = [
        {"id": "i1", "kind": "image", "asset_id": image, "start": 0, "end": 1},
        {"id": "i2", "kind": "image", "asset_id": logo, "start": 1, "end": 2},
    ]

    response = client.patch(f"/api/clips/{clip_id}/tracks", json={"overlays": items})

    assert response.status_code == 200
    assert [i["asset_id"] for i in response.json()["tracks"]["overlays"]] == [
        image,
        logo,
    ]
