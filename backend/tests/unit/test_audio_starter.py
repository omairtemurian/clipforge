"""Tests of the CC0 starter set of Pro Edit sound effects (SPEC-v3 5.5,
TASK-218, proedit/audio/starter and scripts/fetch_starter_sfx.py) with
recorded Freesound answers (respx, no network): only CC0 sounds, the wanted
count, no second download, failed searches, the table of licenses and the
script without a key."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from audio_synth import impact, write_wav
from clipforge import config
from clipforge.assets import list_assets
from clipforge.proedit.audio import freesound
from clipforge.proedit.audio.freesound import FreesoundClient
from clipforge.proedit.audio.starter import (
    STARTER_TAG,
    StarterGroup,
    build_starter_set,
    licenses_markdown,
)
from clipforge.stock.base import StockError
from sqlalchemy import Engine
from sqlmodel import Session

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "freesound"
SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"


@pytest.fixture
def wav_bytes(tmp_path: Path) -> bytes:
    """The bytes of a 1.2 s boom as a WAV file."""
    return write_wav(tmp_path / "boom.wav", impact()).read_bytes()


def recorded(name: str) -> dict[str, Any]:
    """Return the recorded answer in tests/fixtures/freesound/<name>.json."""
    body: dict[str, Any] = json.loads((FIXTURES / f"{name}.json").read_text("utf-8"))
    return body


def starter_group_search(respx_mock: respx.MockRouter, body: dict[str, Any]) -> None:
    respx_mock.get(freesound.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=body)
    )


def test_the_starter_set_keeps_only_cc0_sounds(
    engine: Engine, respx_mock: respx.MockRouter, wav_bytes: bytes
) -> None:
    cc0, by = recorded("sound_cc0"), recorded("sound_cc_by")
    starter_group_search(respx_mock, {"count": 2, "results": [by, cc0]})
    for sound in (cc0, by):
        respx_mock.get(sound["previews"]["preview-hq-mp3"]).mock(
            return_value=httpx.Response(200, content=wav_bytes)
        )
    group = StarterGroup("whoosh", "whoosh", 0.1, 3.0, 5)

    with Session(engine) as session:
        sounds = build_starter_set(FreesoundClient("key"), session, [group])
        stored = list_assets(session)

    assert [s.sound.id for s in sounds] == [cc0["id"]]
    assert [a.id for a in stored] == [sounds[0].asset.id]
    assert stored[0].license.startswith("CC0")
    assert STARTER_TAG in stored[0].tags
    assert stored[0].category == "whoosh"


def test_the_starter_set_is_not_downloaded_twice(
    engine: Engine, respx_mock: respx.MockRouter, wav_bytes: bytes
) -> None:
    cc0 = recorded("sound_cc0")
    starter_group_search(respx_mock, {"count": 1, "results": [cc0]})
    cdn = respx_mock.get(cc0["previews"]["preview-hq-mp3"]).mock(
        return_value=httpx.Response(200, content=wav_bytes)
    )
    group = StarterGroup("whoosh", "whoosh", 0.1, 3.0, 5)

    with Session(engine) as session:
        build_starter_set(FreesoundClient("key"), session, [group])
        again = build_starter_set(FreesoundClient("key"), session, [group])
        count = len(list_assets(session))

    assert (len(again), count, cdn.call_count) == (1, 1, 1)


def test_the_starter_set_stops_at_the_wanted_count(
    engine: Engine, respx_mock: respx.MockRouter, wav_bytes: bytes
) -> None:
    first = recorded("sound_cc0")
    second = {
        **first,
        "id": first["id"] + 1,
        "url": first["url"].replace(str(first["id"]), str(first["id"] + 1)),
    }
    second["previews"] = {"preview-hq-mp3": "https://cdn.freesound.org/previews/2.mp3"}
    starter_group_search(respx_mock, {"count": 2, "results": [first, second]})
    respx_mock.get(first["previews"]["preview-hq-mp3"]).mock(
        return_value=httpx.Response(200, content=wav_bytes)
    )
    unused = respx_mock.get(second["previews"]["preview-hq-mp3"]).mock(
        return_value=httpx.Response(200, content=wav_bytes)
    )

    with Session(engine) as session:
        sounds = build_starter_set(
            FreesoundClient("key"),
            session,
            [StarterGroup("whoosh", "whoosh", 0.1, 3.0, 1)],
        )

    assert len(sounds) == 1
    assert unused.call_count == 0


def test_a_failed_search_stops_the_set_only_if_every_group_failed(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(freesound.SEARCH_URL).mock(return_value=httpx.Response(500))
    group = StarterGroup("whoosh", "whoosh", 0.1, 3.0, 5)

    with Session(engine) as session, pytest.raises(StockError, match="any group"):
        build_starter_set(FreesoundClient("key"), session, [group])


def test_the_table_of_licenses_has_a_row_per_sound_and_no_audio(
    engine: Engine, respx_mock: respx.MockRouter, wav_bytes: bytes
) -> None:
    cc0 = recorded("sound_cc0")
    starter_group_search(respx_mock, {"count": 1, "results": [cc0]})
    respx_mock.get(cc0["previews"]["preview-hq-mp3"]).mock(
        return_value=httpx.Response(200, content=wav_bytes)
    )
    with Session(engine) as session:
        sounds = build_starter_set(
            FreesoundClient("key"),
            session,
            [StarterGroup("whoosh", "whoosh", 0.1, 3.0, 5)],
        )

    table = licenses_markdown(sounds).splitlines()

    assert table[0].startswith("# Starter sound effects")
    rows = [line for line in table if line.startswith("| whoosh")]
    assert len(rows) == 1
    assert sounds[0].sound.page_url in rows[0]
    assert sounds[0].sound.attribution in rows[0]


def test_the_script_without_a_key_says_to_add_one(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setattr(
        config,
        "settings",
        config.settings.model_copy(update={"freesound_api_key": ""}),
    )
    import fetch_starter_sfx

    assert fetch_starter_sfx.main([]) == 1
    assert "Add a Freesound key" in capsys.readouterr().err
