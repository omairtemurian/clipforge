"""Tests for the stock B-roll providers (clipforge.stock): Pexels and
Pixabay searches with responses shaped like the official documentation's
examples (respx; no network), the missing-key path, error answers, usage
metering, the 24 h cache and downloads into the asset library."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
import seed
from clipforge import usage
from clipforge.asset_rows import UsageRecordRow
from clipforge.assets import get_asset, list_assets
from clipforge.config import Settings
from clipforge.models import StockClip
from clipforge.stock import (
    ProviderDisabled,
    StockError,
    download_clip,
    pexels,
    pixabay,
    provider,
    provider_statuses,
)
from clipforge.stock.base import CACHE_SECONDS, SearchCache
from sqlalchemy import Engine
from sqlmodel import Session, select

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
STOCK_FIXTURES = FIXTURES / "stock"
PEXELS_KEY = "pexels-secret"
PIXABAY_KEY = "pixabay-secret"
CDN = "https://cdn.example.com/clip.mp4"


def recorded(name: str) -> dict[str, Any]:
    """Return the recorded answer in tests/fixtures/stock/<name>.json."""
    body: dict[str, Any] = json.loads(
        (STOCK_FIXTURES / f"{name}.json").read_text(encoding="utf-8")
    )
    return body


@pytest.fixture(autouse=True)
def fresh_cache() -> Iterator[None]:
    """Every test starts without cached Pixabay results."""
    pixabay.cache.clear()
    yield
    pixabay.cache.clear()


def api_calls(engine: Engine) -> list[UsageRecordRow]:
    """Return the API_CALLS usage rows."""
    with Session(engine) as session:
        return list(
            session.exec(
                select(UsageRecordRow).where(UsageRecordRow.kind == usage.API_CALLS)
            )
        )


def test_pexels_search_sends_the_key_in_authorization_and_parses_videos(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(pexels.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded("pexels_search"))
    )

    clips = pexels.PexelsClient(PEXELS_KEY).search(
        "forest", orientation="landscape", per_page=2
    )

    request = route.calls.last.request
    assert request.headers["Authorization"] == PEXELS_KEY
    assert dict(request.url.params) == {
        "query": "forest",
        "per_page": "2",
        "orientation": "landscape",
    }
    forest, portrait = clips
    assert forest.provider == "pexels"
    assert forest.provider_id == "1448735"
    assert forest.page_url == "https://www.pexels.com/video/video-of-forest-1448735/"
    assert (forest.width, forest.height) == (2048, 1080)
    assert forest.download_url.endswith("profile_id=175")
    assert forest.duration_s == 32
    assert forest.creator == "Ruvim Miksanskiy"
    assert forest.creator_url == "https://www.pexels.com/@digitech"
    assert forest.license == "Pexels License"
    assert forest.attribution == (
        "Video by Ruvim Miksanskiy on Pexels "
        "(https://www.pexels.com/video/video-of-forest-1448735/)"
    )
    assert (portrait.width, portrait.height) == (1080, 1920)


def test_pexels_skips_hls_and_filters_by_duration(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(pexels.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded("pexels_search"))
    )

    clips = pexels.PexelsClient(PEXELS_KEY).search("forest", min_duration_s=10)

    assert [clip.provider_id for clip in clips] == ["1448735"]


def test_pixabay_search_sends_the_key_param_and_parses_hits(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(pixabay.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded("pixabay_search"))
    )

    flowers, night = pixabay.PixabayClient(PIXABAY_KEY).search("yellow flowers")

    params = route.calls.last.request.url.params
    assert params["key"] == PIXABAY_KEY
    assert params["q"] == "yellow flowers"
    assert flowers.provider == "pixabay"
    assert flowers.page_url == "https://pixabay.com/videos/id-125/"
    assert (flowers.width, flowers.height) == (1920, 1080)
    assert flowers.tags == ["flowers", "yellow", "blossom"]
    assert (
        flowers.creator_url == "https://pixabay.com/users/Coverr-Free-Footage-1281706/"
    )
    assert flowers.license == "Pixabay Content License"
    assert flowers.attribution.startswith("Video by Coverr-Free-Footage on Pixabay")
    assert flowers.preview_url is not None
    # the empty "large" size is not used; 720x1280 is the best that is left
    assert (night.width, night.height) == (720, 1280)


def test_pixabay_filters_by_orientation_and_duration(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(pixabay.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded("pixabay_search"))
    )
    client = pixabay.PixabayClient(PIXABAY_KEY)

    portrait = client.search("city", orientation="portrait")
    long = client.search("city", min_duration_s=10)

    assert [clip.provider_id for clip in portrait] == ["473"]
    assert [clip.provider_id for clip in long] == ["125"]


def test_pixabay_results_are_cached_for_24_hours(
    respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    route = respx_mock.get(pixabay.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded("pixabay_search"))
    )
    now = [1000.0]
    monkeypatch.setattr(pixabay, "cache", SearchCache(clock=lambda: now[0]))
    client = pixabay.PixabayClient(PIXABAY_KEY)

    client.search("flowers")
    now[0] += CACHE_SECONDS - 1
    client.search("flowers")
    assert route.call_count == 1

    now[0] += 2
    client.search("flowers")
    assert route.call_count == 2


@pytest.mark.parametrize("client_type", [pexels.PexelsClient, pixabay.PixabayClient])
def test_a_missing_key_disables_the_provider_with_a_message(client_type: Any) -> None:
    with pytest.raises(ProviderDisabled, match=r"_API_KEY in \.env"):
        client_type("")


def test_provider_and_statuses_follow_the_settings() -> None:
    cfg = Settings(pexels_api_key=PEXELS_KEY, pixabay_api_key="")

    assert provider("pexels", cfg).name == "pexels"
    with pytest.raises(ProviderDisabled, match="PIXABAY_API_KEY"):
        provider("pixabay", cfg)
    pexels_status, pixabay_status = provider_statuses(cfg)
    assert (pexels_status.enabled, pexels_status.message) == (True, "")
    assert pixabay_status.enabled is False
    assert "PIXABAY_API_KEY" in pixabay_status.message
    assert [
        s.enabled
        for s in provider_statuses(Settings(pexels_api_key="", pixabay_api_key=""))
    ] == [False, False]


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "refused the API key"),
        (403, "refused the API key"),
        (429, "rate limit"),
        (500, "HTTP 500"),
    ],
)
def test_error_answers_become_stock_errors(
    respx_mock: respx.MockRouter, status: int, message: str
) -> None:
    respx_mock.get(pexels.SEARCH_URL).mock(return_value=httpx.Response(status))

    with pytest.raises(StockError, match=message):
        pexels.PexelsClient(PEXELS_KEY).search("forest")


def test_a_network_failure_and_a_bad_body_become_stock_errors(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(pixabay.SEARCH_URL)
    client = pixabay.PixabayClient(PIXABAY_KEY)

    route.mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(StockError, match="could not reach Pixabay"):
        client.search("a")
    route.mock(return_value=httpx.Response(200, text="<html>"))
    with pytest.raises(StockError, match="not JSON"):
        client.search("b")
    route.mock(return_value=httpx.Response(200, json=[1]))
    with pytest.raises(StockError, match="unexpected JSON"):
        client.search("c")


def test_each_search_is_an_api_call_for_the_project(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(pexels.SEARCH_URL).mock(
        return_value=httpx.Response(200, json=recorded("pexels_search"))
    )
    project_id = seed.add_project(engine)
    client = pexels.PexelsClient(PEXELS_KEY)

    client.search("outside any context")
    with usage.recording(engine, project_id):
        client.search("forest")
        client.search("ocean")

    rows = api_calls(engine)
    assert [(r.project_id, r.units) for r in rows] == [(project_id, 1), (project_id, 1)]


def test_a_failed_request_and_a_cached_answer_are_counted_right(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(pixabay.SEARCH_URL)
    client = pixabay.PixabayClient(PIXABAY_KEY)

    with usage.recording(engine, None):
        route.mock(return_value=httpx.Response(429))
        with pytest.raises(StockError):
            client.search("flowers")
        route.mock(return_value=httpx.Response(200, json=recorded("pixabay_search")))
        client.search("flowers")
        client.search("flowers")

    assert len(api_calls(engine)) == 2


def clip_at(url: str = CDN, **changes: Any) -> StockClip:
    """A Pexels clip whose file is at url."""
    clip = StockClip(
        provider="pexels",
        provider_id="42",
        page_url="https://www.pexels.com/video/42/",
        preview_url=None,
        download_url=url,
        width=640,
        height=360,
        duration_s=3,
        creator="Ada",
        creator_url=None,
        tags=["sea", "stock"],
        license="Pexels License",
        attribution="Video by Ada on Pexels (https://www.pexels.com/video/42/)",
    )
    return clip.model_copy(update=changes)


def test_download_stores_the_file_as_an_asset_with_license_and_attribution(
    data_dir: Path, engine: Engine, respx_mock: respx.MockRouter
) -> None:
    video = (FIXTURES / "sample.mp4").read_bytes()
    route = respx_mock.get(CDN).mock(return_value=httpx.Response(200, content=video))

    with Session(engine) as session:
        asset = download_clip(session, clip_at())
        stored = get_asset(session, asset.id)

    assert stored == asset
    assert asset.kind == "video"
    assert Path(asset.path) == data_dir / "stock" / "pexels" / "42.mp4"
    assert Path(asset.path).read_bytes() == video
    assert asset.license == "Pexels License"
    assert asset.attribution.startswith("Video by Ada on Pexels")
    assert asset.source_url == "https://www.pexels.com/video/42/"
    assert asset.tags == ["stock", "pexels", "sea"]
    assert "Authorization" not in route.calls.last.request.headers
    assert list(Path(asset.path).parent.glob("*.part")) == []


def test_downloading_a_clip_again_reuses_its_asset(
    data_dir: Path, engine: Engine, respx_mock: respx.MockRouter
) -> None:
    video = (FIXTURES / "sample.mp4").read_bytes()
    route = respx_mock.get(CDN).mock(return_value=httpx.Response(200, content=video))

    with Session(engine) as session:
        first = download_clip(session, clip_at())
        second = download_clip(session, clip_at())
        assert len(list_assets(session, "video")) == 1

    assert second == first
    assert route.call_count == 1


def test_a_download_that_is_not_a_video_keeps_nothing(
    data_dir: Path, engine: Engine, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(CDN).mock(return_value=httpx.Response(200, content=b"<html>no"))

    with Session(engine) as session, pytest.raises(StockError, match="not a video"):
        download_clip(session, clip_at())

    with Session(engine) as session:
        assert list_assets(session) == []
    assert list((data_dir / "stock").rglob("*.*")) == []


def test_a_failed_download_and_an_insecure_link_are_stock_errors(
    data_dir: Path, engine: Engine, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(CDN).mock(return_value=httpx.Response(404))

    with Session(engine) as session:
        with pytest.raises(StockError, match="HTTP 404"):
            download_clip(session, clip_at())
        with pytest.raises(StockError, match="https"):
            download_clip(session, clip_at("http://cdn.example.com/clip.mp4"))
        assert list_assets(session) == []
