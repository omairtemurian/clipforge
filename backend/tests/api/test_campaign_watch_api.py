"""Tests for the creator watch through the campaign endpoints: saving a
campaign registers its YouTube channels in Auto Import, changing its links
or deleting it updates them."""

from campaign_api import CAMPAIGNS, PERMISSION_URL, add, upload
from fastapi.testclient import TestClient
from youtube_fakes import CHANNEL

CHANNELS = "/api/auto-import/channels"
OTHER = "UCaaaaaaaaaaaaaaaaaaaaaa"


def link(channel_id: str) -> str:
    return f"https://www.youtube.com/channel/{channel_id}"


def watched(client: TestClient) -> list[tuple[str, int | None]]:
    return [(c["channel_id"], c["campaign_id"]) for c in client.get(CHANNELS).json()]


def test_a_new_campaign_watches_its_youtube_channels(client: TestClient) -> None:
    campaign = add(
        client,
        source_channel_urls=[link(CHANNEL), "https://www.tiktok.com/@someone"],
        required_credit_line="Clip of the Creator",
    )

    assert watched(client) == [(CHANNEL, campaign["id"])]
    (channel,) = client.get(CHANNELS).json()
    assert (channel["enabled"], channel["credit_line"]) == (
        True,
        "Clip of the Creator",
    )


def test_a_handle_without_the_api_key_does_not_fail_the_save(
    client: TestClient,
) -> None:
    campaign = add(
        client,
        source_channel_urls=[link(CHANNEL), "https://www.youtube.com/@creator"],
    )

    assert campaign["name"] == "Clips"
    assert watched(client) == [(CHANNEL, campaign["id"])]


def test_changing_the_links_changes_the_watch(client: TestClient) -> None:
    campaign = add(client, source_channel_urls=[link(CHANNEL)])

    response = client.patch(
        f"{CAMPAIGNS}/{campaign['id']}", json={"source_channel_urls": [link(OTHER)]}
    )

    assert response.status_code == 200
    assert watched(client) == [(OTHER, campaign["id"])]


def test_pausing_a_campaign_stops_the_watch_and_deleting_removes_it(
    client: TestClient,
) -> None:
    campaign = add(client, source_channel_urls=[link(CHANNEL)])

    client.patch(f"{CAMPAIGNS}/{campaign['id']}", json={"status": "paused"})
    assert client.get(CHANNELS).json()[0]["enabled"] is False

    assert client.delete(f"{CAMPAIGNS}/{campaign['id']}").status_code == 204
    assert client.get(CHANNELS).json() == []


def test_the_permission_screenshot_gives_the_channels_source_rights(
    client: TestClient,
) -> None:
    campaign = add(
        client,
        source_channel_urls=[link(CHANNEL)],
        permission_source_url=PERMISSION_URL,
    )
    assert client.get(CHANNELS).json()[0]["source_rights"] is None

    assert upload(client, campaign["id"]).status_code == 200

    assert client.get(CHANNELS).json()[0]["source_rights"] == "permission"
