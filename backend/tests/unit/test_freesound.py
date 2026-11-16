"""Tests of the Freesound audio library of Pro Edit (SPEC-v3 5.1, 5.6,
TASK-217): searches and downloads with answers shaped like the API
documentation (respx, tests/fixtures/freesound; no network), the CC0 / CC BY
license filter (also on the returned metadata), the rate limiter, the usage
metering, the stored license data and the credits of CC BY sounds."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from clipforge import usage
from clipforge.asset_rows import UsageRecordRow
from clipforge.assets import add_asset, list_assets
from clipforge.config import Settings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.proedit.audio import freesound
from clipforge.proedit.audio.credits import (
    HEADING,
    credit_lines,
    used_assets,
    with_credits,
)
from clipforge.proedit.audio.freesound import (
    FreesoundClient,
    LicenseRejected,
    RateLimiter,
    download_sound,
    parse_sound,
    search_filter,
    tag_term,
)
from clipforge.proedit.audio.licenses import is_allowed, license_label, needs_credit
from clipforge.proedit.edl import SfxItem, parse_item
from clipforge.stock.base import ProviderDisabled, StockError
from edl_fakes import item
from sqlalchemy import Engine
from sqlmodel import Session, select

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "freesound"
KEY = "freesound-secret"
CC_BY_PREVIEW = "https://cdn.freesound.org/previews/361/361492_77-hq.mp3"


def recorded(name: str) -> dict[str, Any]:
    """Return the recorded answer in tests/fixtures/freesound/<name>.json."""
    body: dict[str, Any] = json.loads(
        (FIXTURES / f"{name}.json").read_text(encoding="utf-8")
    )
    return body


@pytest.fixture(scope="module")
def preview_mp3(tmp_path_factory: pytest.TempPathFactory) -> bytes:
    """The bytes of a short MP3, as a Freesound preview."""
    path = tmp_path_factory.mktemp("preview") / "p.mp3"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=440:duration=0.5", str(path)])
    return path.read_bytes()


@pytest.mark.parametrize(
    ("value", "label"),
    [
        ("Creative Commons 0", "CC0 1.0"),
        ("Attribution", "CC BY"),
        (" attribution ", "CC BY"),
        ("http://creativecommons.org/publicdomain/zero/1.0/", "CC0 1.0"),
        ("https://creativecommons.org/licenses/by/4.0/", "CC BY 4.0"),
        ("http://creativecommons.org/licenses/by/3.0", "CC BY 3.0"),
        ("Attribution NonCommercial", None),
        ("Attribution Noncommercial", None),
        ("Sampling+", None),
        ("http://creativecommons.org/licenses/by-nc/3.0/", None),
        ("http://creativecommons.org/licenses/by-sa/4.0/", None),
        ("http://creativecommons.org/licenses/by-nd/4.0/", None),
        ("http://creativecommons.org/licenses/sampling+/1.0/", None),
        ("https://evil.example/creativecommons.org/licenses/by/4.0/", None),
        ("", None),
        (None, None),
        (4, None),
    ],
)
def test_only_cc0_and_cc_by_licenses_have_a_label(
    value: object, label: str | None
) -> None:
    assert license_label(value) == label


def test_allowed_and_credited_labels() -> None:
    assert [is_allowed(x) for x in ("CC0 1.0", "CC BY", "CC BY 4.0", "CC0")] == [
        True
    ] * 4
    assert not any(
        is_allowed(x) for x in ("CC BY-NC 4.0", "CC BY-SA", "Sampling+", "CC0X", "")
    )
    assert [needs_credit(x) for x in ("CC BY", "CC BY 4.0", "CC0 1.0")] == [
        True,
        True,
        False,
    ]


def test_search_sends_the_token_and_asks_for_cc0_and_cc_by_sounds(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(freesound.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded("search_whoosh"))
    )

    FreesoundClient(KEY).search(
        tags=["whoosh", "Air Swish"],
        query="fast",
        min_duration_s=0.2,
        max_duration_s=3,
        page_size=40,
    )

    request = route.calls.last.request
    assert request.headers["Authorization"] == f"Token {KEY}"
    assert KEY not in str(request.url)
    assert dict(request.url.params) == {
        "query": "fast",
        "filter": 'tag:whoosh tag:air-swish duration:[0.2 TO 3] license:("Creative '
        'Commons 0" OR "Attribution")',
        "fields": "id,name,tags,username,license,url,duration,previews",
        "page_size": "40",
    }


def test_search_keeps_only_cc0_and_cc_by_sounds_even_if_the_filter_leaks(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(freesound.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded("search_whoosh"))
    )

    sounds = FreesoundClient(KEY).search(tags=["whoosh"])

    assert [(s.id, s.license) for s in sounds] == [
        (76693, "CC0 1.0"),
        (361492, "CC BY"),
        (530012, "CC BY 4.0"),
        (530013, "CC0 1.0"),
    ]


def test_a_found_sound_has_its_preview_page_and_credit() -> None:
    sound = parse_sound(recorded("sound_cc_by"))

    assert sound is not None
    assert sound.model_dump() == {
        "id": 361492,
        "name": "Whoosh Fast",
        "username": "ejfortin",
        "tags": ["whoosh", "fast", "transition"],
        "duration_s": 1.2,
        "license": "CC BY",
        "page_url": "https://freesound.org/people/ejfortin/sounds/361492/",
        "preview_url": CC_BY_PREVIEW,
        "attribution": '"Whoosh Fast" by ejfortin on Freesound '
        "(https://freesound.org/people/ejfortin/sounds/361492/), CC BY",
    }


def test_the_page_url_is_built_when_the_result_has_no_url() -> None:
    raw = recorded("sound_cc0") | {"url": "https://other.example/x"}

    sound = parse_sound(raw)

    assert sound is not None
    assert sound.page_url == "https://freesound.org/people/moxobna/sounds/76693/"


@pytest.mark.parametrize("bad", [None, [], {}, {"id": "7"}, {"id": 1, "license": 3}])
def test_a_malformed_result_is_not_a_sound(bad: object) -> None:
    assert parse_sound(bad) is None


def test_a_preview_that_is_not_https_is_not_used() -> None:
    raw = recorded("sound_cc0")
    raw["previews"] = {"preview-hq-mp3": "http://cdn.freesound.org/x.mp3"}

    assert parse_sound(raw) is None


def test_the_filter_has_the_tags_the_length_and_the_licenses() -> None:
    assert search_filter([], 0, None) == freesound.FILTER_LICENSE
    assert search_filter(["riser"], 0, 4.5).startswith("tag:riser duration:[0 TO 4.5] ")
    assert search_filter(["riser"], 1, None) == (
        f"tag:riser duration:[1 TO *] {freesound.FILTER_LICENSE}"
    )


@pytest.mark.parametrize("tag", ['a" OR license:x', "bass drop)", "tag:x", "", "  "])
def test_a_tag_cannot_change_the_filter(tag: str) -> None:
    with pytest.raises(ValueError, match="not a Freesound tag"):
        tag_term(tag)


def test_tags_are_lower_case_words_joined_by_dashes() -> None:
    assert tag_term(" Bass  Drop ") == "bass-drop"
    assert tag_term("sfx_1") == "sfx_1"


def test_search_needs_a_tag_or_a_query() -> None:
    with pytest.raises(ValueError, match="needs a tag or a query"):
        FreesoundClient(KEY).search()


def test_search_by_query_alone_and_the_page_size_is_kept_in_range(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(freesound.SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    client = FreesoundClient(KEY)

    assert client.search(query="  glitch  ", page_size=900) == []
    assert client.search(query="glitch", page_size=0) == []

    first, second = (c.request.url.params for c in route.calls)
    assert (first["query"], first["page_size"], second["page_size"]) == (
        "glitch",
        "150",
        "1",
    )


def test_without_a_key_the_library_says_to_add_one() -> None:
    with pytest.raises(ProviderDisabled, match="Add a Freesound key"):
        FreesoundClient("")


def test_the_status_follows_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(freesound.config, "settings", Settings(freesound_api_key=""))
    off = freesound.status()
    monkeypatch.setattr(freesound.config, "settings", Settings(freesound_api_key=KEY))
    on = freesound.status()

    assert (off.enabled, "Add a Freesound key" in off.message) == (False, True)
    assert (on.enabled, on.message) == (True, "")


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "refused the API key"),
        (403, "refused the API key"),
        (429, "rate limit reached"),
        (500, "HTTP 500"),
    ],
)
def test_error_answers_are_stock_errors(
    respx_mock: respx.MockRouter, status: int, message: str
) -> None:
    respx_mock.get(freesound.SEARCH_URL).mock(return_value=httpx.Response(status))

    with pytest.raises(StockError, match=message):
        FreesoundClient(KEY).search(tags=["pop"])


def test_every_request_is_one_metered_api_call(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(freesound.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded("search_whoosh"))
    )

    with usage.recording(engine, None):
        FreesoundClient(KEY).search(tags=["whoosh"])
        FreesoundClient(KEY).search(tags=["pop"])

    with Session(engine) as session:
        rows = session.exec(
            select(UsageRecordRow).where(UsageRecordRow.kind == usage.API_CALLS)
        ).all()
    assert sum(row.units for row in rows) == 2


class Clock:
    """A clock that only moves when the limiter sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_the_limiter_waits_for_a_free_slot_instead_of_exceeding_the_rate() -> None:
    clock = Clock()
    limiter = RateLimiter(
        calls=3, per_s=60, max_wait_s=60, clock=lambda: clock.now, sleep=clock.sleep
    )

    for _ in range(3):
        limiter.acquire()
        clock.now += 1
    limiter.acquire()

    assert clock.slept == [57.0]


def test_the_limiter_refuses_a_wait_longer_than_its_maximum() -> None:
    clock = Clock()
    limiter = RateLimiter(
        calls=1, per_s=60, max_wait_s=5, clock=lambda: clock.now, sleep=clock.sleep
    )
    limiter.acquire()

    with pytest.raises(StockError, match=r"rate limit reached; try again in 60 s"):
        limiter.acquire()
    assert clock.slept == []


def test_the_limiter_frees_slots_as_time_passes() -> None:
    clock = Clock()
    limiter = RateLimiter(calls=2, per_s=60, clock=lambda: clock.now, sleep=clock.sleep)
    limiter.acquire()
    limiter.acquire()
    clock.now += 61

    limiter.acquire()

    assert clock.slept == []


def test_a_client_waits_on_its_limiter_before_each_request(
    respx_mock: respx.MockRouter,
) -> None:
    clock = Clock()
    limiter = RateLimiter(
        calls=1, per_s=60, max_wait_s=60, clock=lambda: clock.now, sleep=clock.sleep
    )
    respx_mock.get(freesound.SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    client = FreesoundClient(KEY, rate_limiter=limiter)

    client.search(tags=["pop"])
    client.search(tags=["pop"])

    assert clock.slept == [60.0]


def test_a_sound_by_id_is_read_with_its_fields(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{freesound.API_URL}/sounds/361492/").mock(
        return_value=httpx.Response(200, json=recorded("sound_cc_by"))
    )

    sound = FreesoundClient(KEY).sound(361492)

    assert sound.license == "CC BY"
    assert route.calls.last.request.url.params["fields"] == freesound.FIELDS


def test_a_sound_with_another_license_is_rejected(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"{freesound.API_URL}/sounds/411089/").mock(
        return_value=httpx.Response(200, json=recorded("sound_by_nc"))
    )

    with pytest.raises(LicenseRejected, match="not CC0 or CC BY"):
        FreesoundClient(KEY).sound(411089)


def test_a_download_stores_the_preview_with_its_license_data(
    engine: Engine, respx_mock: respx.MockRouter, preview_mp3: bytes
) -> None:
    cdn = respx_mock.get(CC_BY_PREVIEW).mock(
        return_value=httpx.Response(200, content=preview_mp3)
    )
    sound = parse_sound(recorded("sound_cc_by"))
    assert sound is not None

    with Session(engine) as session:
        asset = download_sound(session, sound, kind="sfx", category="whoosh")

    assert asset.kind == "sfx"
    assert Path(asset.path).read_bytes() == preview_mp3
    assert Path(asset.path).parent.name == "freesound"
    assert asset.license == "CC BY"
    assert asset.attribution == sound.attribution
    assert asset.source_url == sound.page_url
    assert asset.category == "whoosh"
    assert asset.downloaded_at is not None
    assert asset.tags[:4] == ["freesound", "whoosh", "fast", "transition"]
    assert asset.tags[4:] == [asset.mood, "sharp-attack"]
    assert asset.energy_curve == [1.0]
    assert asset.loudness_lufs == pytest.approx(-22.2, abs=1)
    assert "Authorization" not in cdn.calls.last.request.headers
    assert not list(Path(asset.path).parent.glob("*.part"))


def test_a_sound_that_was_downloaded_is_not_downloaded_again(
    engine: Engine, respx_mock: respx.MockRouter, preview_mp3: bytes
) -> None:
    cdn = respx_mock.get(CC_BY_PREVIEW).mock(
        return_value=httpx.Response(200, content=preview_mp3)
    )
    sound = parse_sound(recorded("sound_cc_by"))
    assert sound is not None

    with Session(engine) as session:
        first = download_sound(session, sound)
        second = download_sound(session, sound)
        count = len(list_assets(session))

    assert (second.id, count, cdn.call_count) == (first.id, 1, 1)


def test_a_sound_whose_file_was_deleted_is_downloaded_again(
    engine: Engine, respx_mock: respx.MockRouter, preview_mp3: bytes
) -> None:
    cdn = respx_mock.get(CC_BY_PREVIEW).mock(
        return_value=httpx.Response(200, content=preview_mp3)
    )
    sound = parse_sound(recorded("sound_cc_by"))
    assert sound is not None

    with Session(engine) as session:
        first = download_sound(session, sound)
        Path(first.path).unlink()
        again = download_sound(session, sound)

    assert cdn.call_count == 2
    assert Path(again.path).is_file()


@pytest.mark.parametrize("label", ["CC BY-NC 4.0", "CC BY-SA 4.0", "Sampling+", ""])
def test_a_sound_with_a_not_allowed_license_is_not_downloaded(
    engine: Engine, respx_mock: respx.MockRouter, label: str
) -> None:
    sound = parse_sound(recorded("sound_cc_by"))
    assert sound is not None

    with Session(engine) as session, pytest.raises(LicenseRejected):
        download_sound(session, sound.model_copy(update={"license": label}))

    assert respx_mock.calls.call_count == 0
    with Session(engine) as session:
        assert list_assets(session) == []


def test_a_download_that_is_not_audio_keeps_nothing(
    engine: Engine, respx_mock: respx.MockRouter, data_dir: Path
) -> None:
    respx_mock.get(CC_BY_PREVIEW).mock(
        return_value=httpx.Response(200, content=b"<html>not a sound</html>")
    )
    sound = parse_sound(recorded("sound_cc_by"))
    assert sound is not None

    with Session(engine) as session, pytest.raises(StockError, match="not audio"):
        download_sound(session, sound)

    assert list((data_dir / "audio" / "freesound").iterdir()) == []
    with Session(engine) as session:
        assert list_assets(session) == []


def test_a_failed_download_keeps_nothing(
    engine: Engine, respx_mock: respx.MockRouter, data_dir: Path
) -> None:
    respx_mock.get(CC_BY_PREVIEW).mock(return_value=httpx.Response(404))
    sound = parse_sound(recorded("sound_cc_by"))
    assert sound is not None

    with Session(engine) as session, pytest.raises(StockError, match="HTTP 404"):
        download_sound(session, sound)

    assert list((data_dir / "audio" / "freesound").iterdir()) == []


def stored(engine: Engine, name: str, preview: bytes, mp3: Path) -> int:
    """Add the asset of sound recording `name` (the file is mp3) and return
    its id."""
    sound = parse_sound(recorded(name))
    assert sound is not None
    mp3.write_bytes(preview)
    with Session(engine) as session:
        return add_asset(
            session,
            "sfx",
            str(mp3),
            sound.license,
            attribution=sound.attribution,
            source_url=sound.page_url,
        ).id


def sfx(item_id: int, asset: str) -> SfxItem:
    parsed = parse_item(
        item(item_id, "sfx", float(item_id), item_id + 0.5, params={"asset": asset})
    )
    assert isinstance(parsed, SfxItem)
    return parsed


@pytest.fixture
def library(
    engine: Engine, tmp_path: Path, preview_mp3: bytes
) -> Iterator[dict[str, int]]:
    """Library assets: a CC BY sound, a CC0 sound and a user's own sound
    without a credit."""
    ids = {
        "by": stored(engine, "sound_cc_by", preview_mp3, tmp_path / "by.mp3"),
        "zero": stored(engine, "sound_cc0", preview_mp3, tmp_path / "zero.mp3"),
    }
    with Session(engine) as session:
        ids["own"] = add_asset(
            session, "sfx", str(tmp_path / "own.mp3"), "own recording"
        ).id
    yield ids


def test_only_cc_by_sounds_are_credited(
    engine: Engine, library: dict[str, int]
) -> None:
    items = [
        sfx(1, str(library["zero"])),
        sfx(2, str(library["by"])),
        sfx(3, str(library["by"])),
        sfx(4, str(library["own"])),
        sfx(5, "whoosh_swift"),
        sfx(6, "9999"),
    ]

    with Session(engine) as session:
        assets = used_assets(session, items)

    assert [a.id for a in assets] == [library["zero"], library["by"], library["own"]]
    assert credit_lines(assets) == [
        '"Whoosh Fast" by ejfortin on Freesound '
        "(https://freesound.org/people/ejfortin/sounds/361492/), CC BY"
    ]


def test_credits_are_appended_once_under_a_heading() -> None:
    text = with_credits("Best pizza", ["A by x", "B by y"])

    assert text == f"Best pizza\n\n{HEADING}\n- A by x\n- B by y"
    assert with_credits(text, ["A by x", "B by y"]) == text
    assert with_credits(text, ["A by x", "C by z"]) == f"{text}\n- C by z"
    assert with_credits("Best pizza", []) == "Best pizza"
    assert with_credits("", ["A by x"]) == f"{HEADING}\n- A by x"
