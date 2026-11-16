"""Caption template endpoints and their preview PNGs."""

import struct
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge import caption_previews
from clipforge.api.app import create_app
from clipforge.captions_templates import load_templates
from fastapi.testclient import TestClient

NAMES = sorted(load_templates())


def png_size(data: bytes) -> tuple[int, int]:
    """Return the (width, height) of a PNG, after checking its signature."""
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_startup_draws_a_valid_png_per_template(data_dir: Path) -> None:
    with TestClient(create_app(run_worker=False)) as client:
        images = sorted((data_dir / "caption_previews").glob("*.png"))
        assert [p.name.rsplit("-", 1)[0] for p in images] == NAMES
        for image in images:
            assert png_size(image.read_bytes()) == (540, 960)

        listed = client.get("/api/caption-templates").json()

    assert [item["name"] for item in listed] == NAMES
    assert len(NAMES) >= 10


def test_list_gives_each_template_and_a_preview_url(client: TestClient) -> None:
    listed = client.get("/api/caption-templates").json()

    neon = next(item for item in listed if item["name"] == "neon")
    assert neon["template"]["font"] == "Montserrat ExtraBold"
    assert neon["template"]["uppercase"] is True
    assert neon["preview_url"] == "/api/caption-templates/neon/preview.png"


@pytest.mark.parametrize("name", NAMES)
def test_every_preview_url_serves_a_png(client: TestClient, name: str) -> None:
    url = f"/api/caption-templates/{name}/preview.png"

    response = client.get(url)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert png_size(response.content) == (540, 960)


def test_the_preview_is_not_a_blank_frame(client: TestClient) -> None:
    flat = client.get("/api/caption-templates/neon/preview.png").content
    other = client.get("/api/caption-templates/boxed/preview.png").content

    assert flat != other
    assert len(set(flat)) > 20


def test_unknown_template_is_404(client: TestClient) -> None:
    response = client.get("/api/caption-templates/nope/preview.png")

    assert_error(response, 404, "not_found")


def test_a_cached_preview_is_not_drawn_again(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = "/api/caption-templates/minimal/preview.png"
    first = client.get(url).content
    runs: list[object] = []
    monkeypatch.setattr(caption_previews, "run_ffmpeg", lambda *a, **k: runs.append(a))

    assert client.get(url).content == first
    assert runs == []


def test_a_changed_template_gets_a_new_image_and_the_old_one_goes(
    data_dir: Path,
) -> None:
    template = load_templates()["minimal"]
    old = caption_previews.ensure_preview("minimal", template)

    new = caption_previews.ensure_preview(
        "minimal", template.model_copy(update={"primary_color": "#123456"})
    )

    assert new != old and new.is_file() and not old.exists()
    assert new.parent == data_dir / "caption_previews"
