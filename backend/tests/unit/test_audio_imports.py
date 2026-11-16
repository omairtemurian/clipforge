"""Tests of the Pixabay import, own audio uploads and the CC0 starter set of
Pro Edit (SPEC-v3 5.2, 5.3, 5.5, TASK-218): the URL, license and rights
checks, the stored license data and tags, duplicates, files that are not
audio, and the starter set with recorded Freesound answers (respx, no
network)."""

import io
import json
from pathlib import Path
from typing import Any

import pytest
from audio_synth import impact, write_wav
from clipforge.assets import list_assets
from clipforge.proedit.audio.library import (
    AudioFileError,
    DuplicateAudio,
    store_own_upload,
)
from clipforge.proedit.audio.pixabay import (
    PIXABAY_LICENSE,
    audio_kind,
    import_pixabay_file,
    status,
)
from sqlalchemy import Engine
from sqlmodel import Session

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "freesound"
MUSIC_PAGE = "https://pixabay.com/music/beats-night-drive-123456/"
SFX_PAGE = "https://pixabay.com/sound-effects/whoosh-fast-654321/"


@pytest.fixture
def wav_bytes(tmp_path: Path) -> bytes:
    """The bytes of a 1.2 s boom as a WAV file."""
    return write_wav(tmp_path / "boom.wav", impact()).read_bytes()


def recorded(name: str) -> dict[str, Any]:
    """Return the recorded answer in tests/fixtures/freesound/<name>.json."""
    body: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))
    return body


@pytest.mark.parametrize(
    ("url", "kind"),
    [(MUSIC_PAGE, "music"), (SFX_PAGE, "sfx"), (f" {SFX_PAGE} ", "sfx")],
)
def test_the_page_says_whether_a_pixabay_file_is_music_or_an_effect(
    url: str, kind: str
) -> None:
    assert audio_kind(url) == kind


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://pixabay.com/music/x-1/",
        "https://pixabay.com/photos/x-1/",
        "https://pixabay.com/music/",
        "https://example.com/music/x-1/",
        "https://pixabay.com.evil.example/music/x-1/",
        "https://www.youtube.com/watch?v=abc",
    ],
)
def test_only_a_pixabay_audio_page_is_a_source(url: str) -> None:
    with pytest.raises(AudioFileError, match="source_url"):
        audio_kind(url)


def test_pixabay_has_no_audio_api() -> None:
    found = status()

    assert not found.api
    assert "images and videos only" in found.message


def test_a_pixabay_import_keeps_license_source_and_tags(
    engine: Engine, wav_bytes: bytes
) -> None:
    with Session(engine) as session:
        asset = import_pixabay_file(
            session,
            io.BytesIO(wav_bytes),
            "whoosh-fast.wav",
            source_url=SFX_PAGE,
            license_confirmed=True,
        )
        assert [a.id for a in list_assets(session)] == [asset.id]

    assert asset.kind == "sfx"
    assert asset.license == PIXABAY_LICENSE
    assert asset.source_url == SFX_PAGE
    assert (
        asset.attribution == f'"whoosh-fast" on Pixabay ({SFX_PAGE}), {PIXABAY_LICENSE}'
    )
    assert asset.downloaded_at is not None
    assert asset.category == "impact"
    assert asset.tags[0] == "pixabay"
    assert asset.loudness_lufs is not None
    assert asset.energy_curve == [pytest.approx(1.0), pytest.approx(0.036, abs=0.02)]
    assert Path(asset.path).is_file()


def test_a_pixabay_music_page_makes_a_music_asset_with_the_given_title(
    engine: Engine, wav_bytes: bytes
) -> None:
    with Session(engine) as session:
        asset = import_pixabay_file(
            session,
            io.BytesIO(wav_bytes),
            "x.wav",
            source_url=MUSIC_PAGE,
            license_confirmed=True,
            title="Night Drive",
            category="loop",
        )

    assert (asset.kind, asset.category) == ("music", "loop")
    assert asset.attribution.startswith('"Night Drive" on Pixabay')


def test_an_import_without_the_license_confirmation_is_refused(
    engine: Engine, wav_bytes: bytes
) -> None:
    with Session(engine) as session, pytest.raises(AudioFileError, match="confirm"):
        import_pixabay_file(
            session,
            io.BytesIO(wav_bytes),
            "x.wav",
            source_url=SFX_PAGE,
            license_confirmed=False,
        )
    with Session(engine) as session:
        assert list_assets(session) == []


def test_a_file_that_is_not_audio_is_refused_and_nothing_is_kept(
    engine: Engine, data_dir: Path
) -> None:
    with Session(engine) as session, pytest.raises(AudioFileError):
        import_pixabay_file(
            session,
            io.BytesIO(b"this is text, not audio"),
            "x.mp3",
            source_url=SFX_PAGE,
            license_confirmed=True,
        )

    with Session(engine) as session:
        assert list_assets(session) == []
    assert not list((data_dir / "media").glob("*/file.*"))


def test_the_same_file_twice_is_a_duplicate(engine: Engine, wav_bytes: bytes) -> None:
    with Session(engine) as session:
        store_own_upload(session, io.BytesIO(wav_bytes), "a.wav", rights="own")
        with pytest.raises(DuplicateAudio):
            store_own_upload(session, io.BytesIO(wav_bytes), "b.wav", rights="own")
        assert len(list_assets(session)) == 1


@pytest.mark.parametrize(
    ("rights", "license"),
    [
        ("own", "Own work"),
        ("permission", "Used with permission"),
        ("public_domain", "Public domain"),
    ],
)
def test_an_own_upload_keeps_its_rights_as_license(
    engine: Engine, wav_bytes: bytes, rights: str, license: str
) -> None:
    with Session(engine) as session:
        asset = store_own_upload(
            session,
            io.BytesIO(wav_bytes),
            "boom.wav",
            rights=rights,  # type: ignore[arg-type]
            kind="audio",
        )

    assert (asset.license, asset.kind, asset.source_url) == (license, "audio", None)
    assert asset.tags[:2] == ["uploaded", "own-upload"]
    assert asset.category == "impact"


def test_a_cc_by_upload_needs_its_credit(engine: Engine, wav_bytes: bytes) -> None:
    with Session(engine) as session:
        with pytest.raises(AudioFileError, match="credit"):
            store_own_upload(session, io.BytesIO(wav_bytes), "a.wav", rights="cc_by")
        asset = store_own_upload(
            session,
            io.BytesIO(wav_bytes),
            "a.wav",
            rights="cc_by",
            attribution=" Boom by Ann ",
        )

    assert (asset.license, asset.attribution) == ("CC BY", "Boom by Ann")
