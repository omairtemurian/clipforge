"""Tests for the Watchlist endpoints (api/watch.py and the @handle lookup of
api/auto_import.py): the watch status, the alerts, the Twitch streamers
(add, list, change, remove; 404, 409, 422) and adding a YouTube channel by
@handle (resolved, 412 without the API key, 422 for an unknown handle).
respx answers with recorded YouTube Data API answers."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from apihelpers import assert_error
from clipforge import config
from clipforge.config import Settings
from clipforge.watch.events import record_event
from clipforge.watch.youtube_handles import CHANNELS_URL
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from youtube_fakes import CHANNEL

STREAMERS = "/api/watch/streamers"
YOUTUBE_API = Path(__file__).resolve().parents[1] / "fixtures" / "youtube_api"


@pytest.fixture
def keys(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = config.settings.model_copy(
        update={
            "youtube_api_key": "yt-key",
            "twitch_client_id": "cid",
            "twitch_client_secret": "csecret",
            "public_callback_url": "https://watch.example.com",
            "auto_import_poll_s": 45.0,
        }
    )
    monkeypatch.setattr(config, "settings", settings)
    return settings


def test_the_status_says_what_the_watch_can_do(
    client: TestClient, keys: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/api/watch/status").json() == {
        "push_available": True,
        "poll_interval_s": 45.0,
        "twitch_configured": True,
        "handles_supported": True,
    }
    monkeypatch.setattr(config, "settings", Settings(data_dir=keys.data_dir))
    assert client.get("/api/watch/status").json() == {
        "push_available": False,
        "poll_interval_s": 60.0,
        "twitch_configured": False,
        "handles_supported": False,
    }


def test_the_alerts_are_listed_newest_first_and_after_an_id(
    client: TestClient, api_engine: Engine
) -> None:
    at = datetime(2026, 10, 31, 14, tzinfo=UTC)
    for video in ("a", "b", "c"):
        record_event(
            api_engine,
            platform="youtube",
            kind="upload",
            external_id=video,
            detected_at=at,
            via="poll",
        )

    events = client.get("/api/watch/events").json()
    assert [e["external_id"] for e in events] == ["c", "b", "a"]
    after = client.get("/api/watch/events", params={"after": events[1]["id"]})
    assert [e["external_id"] for e in after.json()] == ["c"]
    limited = client.get("/api/watch/events", params={"limit": 1}).json()
    assert [e["external_id"] for e in limited] == ["c"]
    assert_error(
        client.get("/api/watch/events", params={"limit": 0}), 422, "validation_error"
    )


def test_streamers_are_added_changed_and_removed(client: TestClient) -> None:
    assert client.get(STREAMERS).json() == []

    added = client.post(STREAMERS, json={"login": "https://www.twitch.tv/Afro"})
    assert added.status_code == 201
    streamer = added.json()
    assert (streamer["login"], streamer["display_name"]) == ("afro", "afro")
    assert (streamer["enabled"], streamer["push_state"]) == (True, "off")
    assert client.get(STREAMERS).json() == [streamer]

    assert_error(client.post(STREAMERS, json={"login": "afro"}), 409, "conflict")
    for bad in ("", "no spaces", "https://example.com/afro", "x" * 26):
        assert_error(
            client.post(STREAMERS, json={"login": bad}), 422, "validation_error"
        )

    url = f"{STREAMERS}/{streamer['id']}"
    assert client.patch(url, json={"enabled": False}).json()["enabled"] is False
    assert_error(client.patch(url, json={"login": "x"}), 422, "validation_error")
    assert client.delete(url).status_code == 204
    assert_error(client.delete(url), 404, "not_found")
    assert_error(client.patch(url, json={"enabled": True}), 404, "not_found")


def test_a_channel_is_added_by_its_handle(
    client: TestClient, keys: Settings, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(CHANNELS_URL).mock(
        return_value=httpx.Response(
            200, content=(YOUTUBE_API / "channels_for_handle.json").read_bytes()
        )
    )

    response = client.post(
        "/api/auto-import/channels", json={"channel": "https://youtube.com/@YouTube"}
    )

    assert response.status_code == 201
    assert response.json()["channel_id"] == CHANNEL
    params = route.calls.last.request.url.params
    assert (params["forHandle"], params["part"], params["key"]) == (
        "@YouTube",
        "id",
        "yt-key",
    )


def test_a_handle_needs_the_api_key_and_a_channel(
    client: TestClient,
    keys: Settings,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respx_mock.get(CHANNELS_URL).mock(
        return_value=httpx.Response(
            200, content=(YOUTUBE_API / "channels_none.json").read_bytes()
        )
    )
    channels = "/api/auto-import/channels"

    message = assert_error(
        client.post(channels, json={"channel": "@nobody-here"}), 422, "validation_error"
    )
    assert "no channel @nobody-here" in message
    monkeypatch.setattr(config, "settings", Settings(data_dir=keys.data_dir))
    message = assert_error(
        client.post(channels, json={"channel": "@YouTube"}), 412, "needs_credentials"
    )
    assert "YOUTUBE_API_KEY" in message and "/channel/" in message
    assert client.get(channels).json() == []
