"""Custom font upload (TASK-91, SPEC-v2 3.4): validation of the font tables,
the font library endpoints, and libass drawing captions with an uploaded
font."""

import re
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from builders import make_clip
from clipforge.captions_templates import style_problems
from clipforge.ffmpeg import run_ffmpeg
from clipforge.fonts import FONTS_DIR, render_fonts_dir, user_fonts_dir
from clipforge.models import CaptionStyle
from clipforge.pipeline.captions import write_captions
from clipforge.pipeline.render_graph import subtitles_filter
from fakes import FIXTURES
from fastapi.testclient import TestClient
from fontfiles import renamed_inter, tiny_otf
from fontTools.ttLib import TTFont
from seed import add_clip, add_project
from sqlalchemy import Engine

FONTSELECT = re.compile(r"fontselect: \((.+?), \d+, \d+\) -> (.+?),")
BUNDLED = [
    "Inter",
    "Inter Bold",
    "Montserrat ExtraBold",
    "Noto Sans Hebrew",
    "Noto Sans Hebrew Bold",
    "Vazirmatn",
    "Vazirmatn Bold",
]


def upload(client: TestClient, data: bytes, name: str = "font.ttf", **form: str) -> Any:
    """POST /fonts with data as the file called name."""
    return client.post("/api/fonts", files={"file": (name, data)}, data=form)


def test_a_ttf_is_validated_stored_and_listed_with_its_names(
    client: TestClient, data_dir: Path
) -> None:
    response = upload(client, renamed_inter("Zed Display"), license="OFL-1.1")

    assert response.status_code == 201
    body = response.json()
    assert body["names"] == ["Zed Display", "Zed Display Bold"]
    assert body["bundled"] is False
    asset = body["asset"]
    assert (asset["kind"], asset["license"]) == ("font", "OFL-1.1")
    assert asset["tags"] == ["uploaded"]
    assert "Inter" in asset["attribution"]
    path = Path(asset["path"])
    assert path.parent == data_dir / "fonts" and path.suffix == ".ttf"
    assert path.read_bytes() == renamed_inter("Zed Display")
    listed = client.get("/api/fonts").json()
    assert [f["asset"]["id"] for f in listed if not f["bundled"]] == [asset["id"]]
    assert {f["asset"]["path"] for f in listed if f["bundled"]} >= {
        str(FONTS_DIR / "Inter-Bold.ttf")
    }


def test_an_otf_with_cff_outlines_is_stored_as_otf(client: TestClient) -> None:
    response = upload(client, tiny_otf("Squares"), "squares.OTF")

    assert response.status_code == 201
    assert response.json()["names"] == ["Squares", "Squares Regular"]
    path = Path(response.json()["asset"]["path"])
    assert path.suffix == ".otf"
    with TTFont(path) as font:
        assert "CFF " in font and "glyf" not in font


def test_the_license_defaults_to_user_supplied(client: TestClient) -> None:
    asset = upload(client, tiny_otf("Squares"), "s.otf").json()["asset"]

    assert asset["license"] == "user-supplied"


def test_an_uploaded_font_can_be_a_brand_font_and_a_caption_font(
    client: TestClient,
) -> None:
    before = client.get("/api/brand-fonts").json()
    assert set(BUNDLED) <= set(before)
    upload(client, renamed_inter("Zed Display"))

    assert client.get("/api/brand-fonts").json() == sorted(
        [*before, "Zed Display", "Zed Display Bold"]
    )
    assert style_problems(CaptionStyle(font="Zed Display Bold")) == []
    assert style_problems(CaptionStyle(font="Nope")) != []


@pytest.mark.parametrize(
    ("data", "name", "message"),
    [
        (b"", "a.ttf", "empty"),
        (b"just some text, not a font", "a.ttf", "cannot be read"),
        (renamed_inter("Zed")[:4096], "a.ttf", "cannot be read"),
        (renamed_inter("Zed"), "a.woff", "must end in .ttf or .otf"),
        (renamed_inter("Zed"), "font", "must end in .ttf or .otf"),
    ],
)
def test_a_file_that_is_not_a_usable_font_is_422_and_stores_nothing(
    client: TestClient, data_dir: Path, data: bytes, name: str, message: str
) -> None:
    response = upload(client, data, name)

    assert message in assert_error(response, 422, "validation_error")
    assert list(user_fonts_dir().glob("*")) == []
    assert all(f["bundled"] for f in client.get("/api/fonts").json())


def test_a_font_without_outlines_is_422(client: TestClient) -> None:
    font = TTFont(FONTS_DIR / "Inter-Bold.ttf")
    del font["glyf"], font["loca"]
    out = BytesIO()
    font.save(out)

    message = assert_error(upload(client, out.getvalue()), 422, "validation_error")

    assert "no outlines" in message


def test_a_font_without_a_windows_name_is_422(client: TestClient) -> None:
    font = TTFont(FONTS_DIR / "Inter-Bold.ttf")
    font["name"].names = [n for n in font["name"].names if n.platformID != 3]
    out = BytesIO()
    font.save(out)

    message = assert_error(upload(client, out.getvalue()), 422, "validation_error")

    assert "Windows family or full name" in message


def test_a_font_with_a_name_that_is_taken_is_409(client: TestClient) -> None:
    assert upload(client, renamed_inter("Zed")).status_code == 201

    same_name = assert_error(upload(client, renamed_inter("Zed")), 409, "conflict")
    bundled = assert_error(
        upload(client, (FONTS_DIR / "Inter-Bold.ttf").read_bytes()), 409, "conflict"
    )

    assert "Zed" in same_name and "Inter" in bundled
    assert len(list(user_fonts_dir().glob("*.ttf"))) == 1


def test_deleting_an_uploaded_font_removes_its_file(client: TestClient) -> None:
    made = upload(client, renamed_inter("Zed")).json()

    response = client.delete(f"/api/fonts/{made['asset']['id']}")

    assert response.status_code == 204
    assert not Path(made["asset"]["path"]).exists()
    assert all(f["bundled"] for f in client.get("/api/fonts").json())
    assert upload(client, renamed_inter("Zed")).status_code == 201


def test_a_bundled_font_and_a_missing_font_cannot_be_deleted(
    client: TestClient,
) -> None:
    bundled = next(f for f in client.get("/api/fonts").json() if f["bundled"])

    assert_error(client.delete(f"/api/fonts/{bundled['asset']['id']}"), 409, "conflict")
    assert_error(client.delete("/api/fonts/9999"), 404, "not_found")
    assert Path(bundled["asset"]["path"]).is_file()


def test_a_font_that_a_brand_template_uses_cannot_be_deleted(
    client: TestClient,
) -> None:
    made = upload(client, renamed_inter("Zed")).json()
    created = client.post(
        "/api/brand-templates",
        data={"name": "Acme", "font": "Zed"},
        files={"logo": ("logo.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)},
    )
    assert created.status_code == 201, created.text

    message = assert_error(
        client.delete(f"/api/fonts/{made['asset']['id']}"), 409, "conflict"
    )

    assert "brand template" in message
    assert Path(made["asset"]["path"]).is_file()


def test_a_font_that_a_clip_caption_style_uses_cannot_be_deleted(
    client: TestClient, api_engine: Engine
) -> None:
    made = upload(client, renamed_inter("Zed")).json()
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80, "Pizza")
    patch = client.patch(
        f"/api/clips/{clip_id}", json={"caption_style": {"font": "Zed"}}
    )
    assert patch.status_code == 200

    message = assert_error(
        client.delete(f"/api/fonts/{made['asset']['id']}"), 409, "conflict"
    )

    assert "clip" in message


def test_render_loads_the_uploaded_font_next_to_the_bundled_ones(
    client: TestClient, data_dir: Path, tmp_path: Path
) -> None:
    assert render_fonts_dir() == FONTS_DIR
    stored = Path(upload(client, renamed_inter("Zed Display")).json()["asset"]["path"])
    clip = make_clip(
        "karaoke_bold",
        start=30.0,
        end=34.0,
        caption_style=CaptionStyle(font="Zed Display Bold"),
    )
    job = tmp_path / "job"
    job.mkdir()
    (job / "transcript.json").write_bytes((FIXTURES / "transcript.json").read_bytes())
    ass = write_captions(job, clip, (1080, 1920), 30)
    assert "Zed Display Bold" in ass.read_text(encoding="utf-8")

    fonts = render_fonts_dir()
    result = run_ffmpeg(
        ["-f", "lavfi", "-i", "color=size=1080x1920:rate=4:duration=4"]
        + ["-vf", subtitles_filter(ass), "-f", "null", "-"],
        loglevel="info",
    )

    assert fonts == data_dir / "fonts-render"
    assert sorted(p.name for p in fonts.iterdir()) == sorted(
        [*(p.name for p in FONTS_DIR.glob("*.ttf")), stored.name]
    )
    log = result.stderr.decode()
    assert dict(FONTSELECT.findall(log)) == {"Zed Display Bold": "ZedDisplay-Bold"}
    assert f"Loading font file '{fonts / stored.name}'" in log
    assert "Glyph 0x" not in log


def test_the_render_fonts_follow_the_uploads(
    client: TestClient, data_dir: Path
) -> None:
    made = upload(client, renamed_inter("Zed")).json()
    merged = render_fonts_dir()
    assert Path(made["asset"]["path"]).name in {p.name for p in merged.iterdir()}

    client.delete(f"/api/fonts/{made['asset']['id']}")

    assert render_fonts_dir() == FONTS_DIR
    assert Path(made["asset"]["path"]).name not in {
        p.name for p in render_fonts_dir().iterdir()
    }
