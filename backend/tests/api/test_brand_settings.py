"""Brand template endpoints: CRUD, uploads and validation (TASK-35)."""

import struct
import zlib
from pathlib import Path
from typing import Any

import pytest
from apihelpers import assert_error
from fastapi.testclient import TestClient

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
WEBP = b"RIFF\x1a\x00\x00\x00WEBPVP8 " + b"\x00" * 16


def png() -> bytes:
    """Return a valid 2x2 PNG."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + b"\xff\x6b\x35" * 2 for _ in range(2))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def create(client: TestClient, files: dict[str, Any] | None = None, **form: str) -> Any:
    """POST /brand-templates with a PNG logo unless files say otherwise."""
    uploads = {"logo": ("logo.png", png(), "image/png")} if files is None else files
    data = {"name": "Acme", **form}
    return client.post("/api/brand-templates", data=data, files=uploads or None)


def test_create_returns_the_template_with_its_logo_stored(
    client: TestClient, data_dir: Path
) -> None:
    response = create(
        client,
        logo_position="tl",
        logo_opacity="0.5",
        font="Montserrat ExtraBold",
        primary_color="#112233",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Acme"
    assert body["logo_position"] == "tl"
    assert body["logo_opacity"] == 0.5
    assert body["font"] == "Montserrat ExtraBold"
    assert body["primary_color"] == "#112233"
    assert body["intro_path"] is None and body["outro_path"] is None
    logo = Path(body["logo_path"])
    assert logo == data_dir / "brand" / str(body["id"]) / "logo.png"
    assert logo.read_bytes() == png()


def test_create_defaults(client: TestClient) -> None:
    body = create(client).json()

    assert body["logo_position"] == "br"
    assert body["logo_opacity"] == 0.8
    assert body["font"] == "Inter Bold"
    assert body["primary_color"] == "#FF6B35"


@pytest.mark.parametrize(("data", "suffix"), [(JPEG, ".jpg"), (WEBP, ".webp")])
def test_logo_type_comes_from_its_bytes_not_its_name(
    client: TestClient, data: bytes, suffix: str
) -> None:
    response = create(client, {"logo": ("../../evil.exe", data, "image/x")})

    assert response.status_code == 201
    assert Path(response.json()["logo_path"]).name == f"logo{suffix}"


def test_list_get_and_logo_download(client: TestClient) -> None:
    assert client.get("/api/brand-templates").json() == []
    first = create(client, name="One").json()
    second = create(client, name="Two").json()

    listed = client.get("/api/brand-templates").json()
    assert listed == [first, second]
    assert client.get(f"/api/brand-templates/{second['id']}").json() == second
    logo = client.get(f"/api/brand-templates/{first['id']}/logo")
    assert logo.status_code == 200
    assert logo.content == png()


@pytest.mark.parametrize(
    ("form", "files", "field"),
    [
        ({"name": "  "}, None, "name"),
        ({"logo_position": "center"}, None, "logo_position"),
        ({"logo_opacity": "1.5"}, None, "logo_opacity"),
        ({"logo_opacity": "high"}, None, "logo_opacity"),
        ({"primary_color": "orange"}, None, "primary_color"),
        ({"font": "Comic Sans"}, None, "font"),
        ({}, {}, "logo"),
        ({}, {"logo": ("logo.png", b"", "image/png")}, "logo"),
        ({}, {"logo": ("logo.gif", b"GIF89a....", "image/gif")}, "logo"),
        ({}, {"logo": ("big.png", png() + b"\0" * (5 * 1024 * 1024), "x")}, "logo"),
        ({}, {"logo": ("a.png", png(), "x"), "intro": ("i.mp4", b"no", "x")}, "intro"),
        ({}, {"logo": ("a.png", png(), "x"), "outro": ("o.txt", b"no", "x")}, "outro"),
    ],
)
def test_create_rejects_invalid_input_and_stores_nothing(
    client: TestClient,
    data_dir: Path,
    form: dict[str, str],
    files: dict[str, Any] | None,
    field: str,
) -> None:
    response = create(client, files, **form)

    message = assert_error(response, 422, "validation_error")
    assert field in message
    assert client.get("/api/brand-templates").json() == []
    brand = data_dir / "brand"
    assert not any(path.is_file() for path in brand.rglob("*"))


def test_unknown_template_is_404(client: TestClient) -> None:
    for call in (
        client.get("/api/brand-templates/9"),
        client.put("/api/brand-templates/9", data={"name": "x"}),
        client.delete("/api/brand-templates/9"),
        client.get("/api/brand-templates/9/logo"),
    ):
        assert_error(call, 404, "not_found")


def test_put_changes_only_the_given_fields(client: TestClient) -> None:
    made = create(client, logo_opacity="0.3").json()

    response = client.put(
        f"/api/brand-templates/{made['id']}",
        data={"name": "Renamed", "logo_position": "bl"},
    )

    assert response.status_code == 200
    assert response.json() == {
        **made,
        "name": "Renamed",
        "logo_position": "bl",
    }
    assert client.get(f"/api/brand-templates/{made['id']}").json() == response.json()


def test_put_replaces_the_logo_and_removes_the_old_file(client: TestClient) -> None:
    made = create(client).json()
    old = Path(made["logo_path"])

    response = client.put(
        f"/api/brand-templates/{made['id']}",
        files={"logo": ("new.jpg", JPEG, "image/jpeg")},
    )

    new = Path(response.json()["logo_path"])
    assert new.name == "logo.jpg" and new.read_bytes() == JPEG
    assert not old.exists()


@pytest.mark.parametrize(
    ("form", "files", "field"),
    [
        ({"font": "Nope"}, None, "font"),
        ({"logo_opacity": "-1"}, None, "logo_opacity"),
        ({"name": "   "}, None, "name"),
        ({}, {"logo": ("x.png", b"not an image", "x")}, "logo"),
    ],
)
def test_put_rejects_invalid_input_and_changes_nothing(
    client: TestClient,
    form: dict[str, str],
    files: dict[str, Any] | None,
    field: str,
) -> None:
    made = create(client).json()

    response = client.put(f"/api/brand-templates/{made['id']}", data=form, files=files)

    assert field in assert_error(response, 422, "validation_error")
    assert client.get(f"/api/brand-templates/{made['id']}").json() == made


def test_put_with_a_bad_video_keeps_the_new_logo_out_too(client: TestClient) -> None:
    made = create(client).json()

    response = client.put(
        f"/api/brand-templates/{made['id']}",
        files={
            "logo": ("new.jpg", JPEG, "image/jpeg"),
            "intro": ("intro.mp4", b"not a video", "video/mp4"),
        },
    )

    assert_error(response, 422, "validation_error")
    assert Path(made["logo_path"]).read_bytes() == png()
    assert not Path(made["logo_path"]).with_name("logo.jpg").exists()


def test_intro_and_outro_upload_replace_and_remove(
    client: TestClient, sample_mp4: Path
) -> None:
    made = create(client).json()
    video = sample_mp4.read_bytes()

    both = client.put(
        f"/api/brand-templates/{made['id']}",
        files={
            "intro": ("intro.mp4", video, "video/mp4"),
            "outro": ("outro.mov", video, "video/quicktime"),
        },
    ).json()
    intro, outro = Path(both["intro_path"]), Path(both["outro_path"])
    assert intro.name == "intro.mp4" and intro.read_bytes() == video
    assert outro.name == "outro.mov"

    changed = client.put(
        f"/api/brand-templates/{made['id']}",
        data={"remove_intro": "true"},
        files={"outro": ("again.mp4", video, "video/mp4")},
    ).json()
    assert changed["intro_path"] is None and not intro.exists()
    assert Path(changed["outro_path"]).name == "outro.mp4" and not outro.exists()


def test_delete_removes_the_row_and_its_files(client: TestClient) -> None:
    made = create(client).json()
    directory = Path(made["logo_path"]).parent

    response = client.delete(f"/api/brand-templates/{made['id']}")

    assert response.status_code == 204 and response.content == b""
    assert not directory.exists()
    assert_error(client.get(f"/api/brand-templates/{made['id']}"), 404, "not_found")
    assert client.get("/api/brand-templates").json() == []


def test_brand_fonts_lists_the_bundled_fonts_a_template_accepts(
    client: TestClient,
) -> None:
    fonts = client.get("/api/brand-fonts").json()

    assert fonts == sorted(fonts)
    assert {
        "Inter",
        "Inter Bold",
        "Montserrat ExtraBold",
        "Noto Sans Hebrew",
        "Noto Sans Hebrew Bold",
        "Vazirmatn",
        "Vazirmatn Bold",
        "Anton",
        "Bebas Neue",
        "Luckiest Guy",
        "Poppins Black",
    } <= set(fonts)
    for font in fonts:
        assert create(client, font=font).status_code == 201
