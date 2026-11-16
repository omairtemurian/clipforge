"""Tests for the Auto Import endpoints (api/auto_import.py): add, list, get,
change and remove a watched channel (happy path, 404, 409, 422) and the
videos seen in a channel's feed, with the recorded feeds (respx)."""

import respx
from apihelpers import assert_error
from clipforge.watch.youtube_watcher import AutoImporter
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from youtube_fakes import CHANNEL, MIDDLE, NEWEST, OLDEST, feed_route

CHANNELS = "/api/auto-import/channels"
CHANNEL_LINK = f"https://www.youtube.com/channel/{CHANNEL}"
OTHER = "UCaaaaaaaaaaaaaaaaaaaaaa"


def add(client: TestClient, **body: object) -> dict[str, object]:
    response = client.post(CHANNELS, json={"channel": CHANNEL_LINK, **body})
    assert response.status_code == 201
    channel: dict[str, object] = response.json()
    return channel


def test_a_channel_is_added_with_defaults_and_listed(client: TestClient) -> None:
    assert client.get(CHANNELS).json() == []

    added = add(
        client,
        settings={"genre": "comedy", "num_clips": 3},
        source_rights="permission",
        credit_line="Video by YouTube",
        auto_schedule_drafts=True,
    )

    assert added["channel_id"] == CHANNEL
    assert added["enabled"] is True
    assert (added["last_checked_at"], added["last_error"]) == (None, None)
    assert added["source_rights"] == "permission"
    assert added["credit_line"] == "Video by YouTube"
    assert added["auto_schedule_drafts"] is True
    settings = added["settings"]
    assert isinstance(settings, dict)
    assert (settings["genre"], settings["num_clips"]) == ("comedy", 3)
    assert client.get(CHANNELS).json() == [added]
    assert client.get(f"{CHANNELS}/{added['id']}").json() == added


def test_a_channel_added_with_only_its_id_gets_the_built_in_defaults(
    client: TestClient,
) -> None:
    response = client.post(CHANNELS, json={"channel": CHANNEL})

    body = response.json()
    assert response.status_code == 201
    assert body["settings"]["genre"] == "auto"
    assert (body["source_rights"], body["credit_line"]) == (None, "")
    assert body["auto_schedule_drafts"] is False


def test_a_channel_that_is_watched_cannot_be_added_again(client: TestClient) -> None:
    add(client)

    again = client.post(CHANNELS, json={"channel": CHANNEL})

    assert_error(again, 409, "conflict")
    assert len(client.get(CHANNELS).json()) == 1


def test_a_channel_needs_a_valid_id_or_link_and_valid_defaults(
    client: TestClient,
) -> None:
    for body in (
        {},
        {"channel": "@x"},
        {"channel": "https://example.com/channel/" + CHANNEL},
        {"channel": CHANNEL, "settings": {"num_clips": 0}},
        {"channel": CHANNEL, "source_rights": "stolen"},
        {"channel": CHANNEL, "credit_line": "x" * 201},
        {"channel": CHANNEL, "enabled": "maybe", "settings": {"genre": "nope"}},
    ):
        assert_error(client.post(CHANNELS, json=body), 422, "validation_error")
    assert client.get(CHANNELS).json() == []


def test_only_the_fields_sent_change(client: TestClient) -> None:
    channel = add(client, credit_line="Video by YouTube", source_rights="own")

    changed = client.patch(
        f"{CHANNELS}/{channel['id']}",
        json={"settings": {"genre": "gaming", "aspect": "1:1"}, "enabled": False},
    )

    body = changed.json()
    assert changed.status_code == 200
    assert (body["settings"]["genre"], body["settings"]["aspect"]) == ("gaming", "1:1")
    assert body["enabled"] is False
    assert (body["credit_line"], body["source_rights"]) == ("Video by YouTube", "own")
    assert body["channel_id"] == CHANNEL
    assert client.get(f"{CHANNELS}/{channel['id']}").json() == body


def test_a_patch_can_unset_the_rights_and_change_the_credit_line(
    client: TestClient,
) -> None:
    channel = add(client, source_rights="own", auto_schedule_drafts=True)

    body = client.patch(
        f"{CHANNELS}/{channel['id']}",
        json={
            "source_rights": None,
            "credit_line": "Ann",
            "auto_schedule_drafts": False,
        },
    ).json()

    assert body["source_rights"] is None
    assert (body["credit_line"], body["auto_schedule_drafts"]) == ("Ann", False)


def test_an_invalid_patch_is_refused(client: TestClient) -> None:
    channel = add(client)
    url = f"{CHANNELS}/{channel['id']}"

    for body in (
        {},
        {"channel_id": OTHER},
        {"settings": {"length_presets": []}},
        {"source_rights": "stolen"},
        {"enabled": "maybe"},
    ):
        assert_error(client.patch(url, json=body), 422, "validation_error")
    assert client.get(url).json() == channel


def test_a_removed_channel_is_gone_and_can_be_added_again(
    client: TestClient,
) -> None:
    channel = add(client)
    url = f"{CHANNELS}/{channel['id']}"

    assert client.delete(url).status_code == 204

    assert client.get(CHANNELS).json() == []
    assert_error(client.get(url), 404, "not_found")
    assert add(client)["id"] != channel["id"]


def test_an_unknown_channel_is_404(client: TestClient) -> None:
    for response in (
        client.get(f"{CHANNELS}/99"),
        client.patch(f"{CHANNELS}/99", json={"enabled": False}),
        client.delete(f"{CHANNELS}/99"),
        client.get(f"{CHANNELS}/99/videos"),
    ):
        assert_error(response, 404, "not_found")


def test_the_videos_of_a_channel_show_the_projects_made_for_them(
    client: TestClient, api_engine: Engine, respx_mock: respx.MockRouter
) -> None:
    channel = add(client, source_rights="permission")
    url = f"{CHANNELS}/{channel['id']}/videos"
    assert client.get(url).json() == []
    feed_route(respx_mock, "feed_before", "feed_after")
    importer = AutoImporter(api_engine)

    importer.poll()
    (project_id,) = importer.poll()

    videos = client.get(url).json()
    assert {v["video_id"]: v["project_id"] for v in videos} == {
        NEWEST: project_id,
        MIDDLE: None,
        OLDEST: None,
    }
    assert all(v["watched_channel_id"] == channel["id"] for v in videos)
    checked = client.get(f"{CHANNELS}/{channel['id']}").json()
    assert checked["last_checked_at"] is not None
    assert client.get(f"/api/projects/{project_id}").status_code == 200

    client.delete(f"{CHANNELS}/{channel['id']}")
    assert client.get(f"/api/projects/{project_id}").status_code == 200
