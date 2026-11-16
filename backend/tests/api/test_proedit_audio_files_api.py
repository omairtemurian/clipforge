"""Tests of the Pixabay import and own audio upload endpoints of Pro Edit
(SPEC-v3 5.2-5.4, TASK-218, api/proedit_audio_files): the multipart forms,
the required rights and license confirmation (422), duplicates (409), the
stored tags and the proedit flag."""

from pathlib import Path

import pytest
from apihelpers import assert_error
from audio_synth import impact, write_wav
from clipforge import config
from clipforge.assets import get_asset
from clipforge.proedit.config import ProEditConfig
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session

PREFIX = "/api/proedit/audio"
SFX_PAGE = "https://pixabay.com/sound-effects/boom-9-1/"


@pytest.fixture
def boom(tmp_path: Path) -> bytes:
    """The bytes of a 1.2 s boom as a WAV file."""
    return write_wav(tmp_path / "boom.wav", impact()).read_bytes()


def test_the_pixabay_status_says_there_is_no_audio_api(client: TestClient) -> None:
    body = client.get(f"{PREFIX}/pixabay").json()

    assert body["api"] is False
    assert "images and videos only" in body["message"]


def test_a_pixabay_file_is_imported_and_tagged(
    client: TestClient, api_engine: Engine, boom: bytes
) -> None:
    response = client.post(
        f"{PREFIX}/pixabay/import",
        files={"file": ("boom.wav", boom, "audio/wav")},
        data={"source_url": SFX_PAGE, "license_confirmed": "true", "title": "Boom"},
    )

    assert response.status_code == 201
    asset = response.json()
    assert asset["kind"] == "sfx"
    assert asset["license"] == "Pixabay Content License"
    assert asset["source_url"] == SFX_PAGE
    assert asset["category"] == "impact"
    assert asset["mood"] in ("calm", "medium", "intense")
    assert asset["loudness_lufs"] is not None
    assert asset["energy_curve"]
    assert asset["downloaded_at"] is not None
    with Session(api_engine) as session:
        assert get_asset(session, asset["id"]) is not None


def test_a_pixabay_import_without_confirmation_is_422(
    client: TestClient, boom: bytes
) -> None:
    response = client.post(
        f"{PREFIX}/pixabay/import",
        files={"file": ("boom.wav", boom, "audio/wav")},
        data={"source_url": SFX_PAGE, "license_confirmed": "false"},
    )

    assert "confirm" in assert_error(response, 422, "validation_error")


def test_a_pixabay_import_from_another_site_is_422(
    client: TestClient, boom: bytes
) -> None:
    response = client.post(
        f"{PREFIX}/pixabay/import",
        files={"file": ("boom.wav", boom, "audio/wav")},
        data={"source_url": "https://example.com/boom", "license_confirmed": "true"},
    )

    assert "source_url" in assert_error(response, 422, "validation_error")


def test_an_upload_stores_the_rights_as_its_license(
    client: TestClient, boom: bytes
) -> None:
    response = client.post(
        f"{PREFIX}/uploads",
        files={"file": ("boom.wav", boom, "audio/wav")},
        data={"rights": "own", "kind": "audio", "category": "boom"},
    )

    assert response.status_code == 201
    asset = response.json()
    assert (asset["license"], asset["kind"], asset["category"]) == (
        "Own work",
        "audio",
        "boom",
    )
    assert asset["tags"][:2] == ["uploaded", "own-upload"]


def test_an_upload_without_the_rights_field_is_422(
    client: TestClient, boom: bytes
) -> None:
    response = client.post(
        f"{PREFIX}/uploads", files={"file": ("boom.wav", boom, "audio/wav")}
    )

    assert "rights" in assert_error(response, 422, "validation_error")


@pytest.mark.parametrize("rights", ["", "other", "yes"])
def test_an_upload_with_an_unknown_rights_value_is_422(
    client: TestClient, boom: bytes, rights: str
) -> None:
    response = client.post(
        f"{PREFIX}/uploads",
        files={"file": ("boom.wav", boom, "audio/wav")},
        data={"rights": rights},
    )

    assert_error(response, 422, "validation_error")


def test_a_cc_by_upload_without_credit_is_422(client: TestClient, boom: bytes) -> None:
    response = client.post(
        f"{PREFIX}/uploads",
        files={"file": ("boom.wav", boom, "audio/wav")},
        data={"rights": "cc_by"},
    )

    assert "credit" in assert_error(response, 422, "validation_error")


def test_an_upload_that_is_not_audio_is_422(client: TestClient) -> None:
    response = client.post(
        f"{PREFIX}/uploads",
        files={"file": ("x.mp3", b"plain text, no sound", "audio/mpeg")},
        data={"rights": "own"},
    )

    assert_error(response, 422, "validation_error")


def test_the_same_upload_twice_is_409(client: TestClient, boom: bytes) -> None:
    send = {
        "files": {"file": ("boom.wav", boom, "audio/wav")},
        "data": {"rights": "own"},
    }
    assert client.post(f"{PREFIX}/uploads", **send).status_code == 201

    assert_error(client.post(f"{PREFIX}/uploads", **send), 409, "conflict")


def test_the_endpoints_answer_proedit_disabled_when_it_is_off(
    client: TestClient, boom: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    off = config.settings.model_copy(update={"proedit": ProEditConfig(enabled=False)})
    monkeypatch.setattr(config, "settings", off)
    files = {"file": ("boom.wav", boom, "audio/wav")}

    assert_error(client.get(f"{PREFIX}/pixabay"), 404, "proedit_disabled")
    assert_error(
        client.post(
            f"{PREFIX}/pixabay/import",
            files=files,
            data={"source_url": SFX_PAGE, "license_confirmed": "true"},
        ),
        404,
        "proedit_disabled",
    )
    assert_error(
        client.post(f"{PREFIX}/uploads", files=files, data={"rights": "own"}),
        404,
        "proedit_disabled",
    )
