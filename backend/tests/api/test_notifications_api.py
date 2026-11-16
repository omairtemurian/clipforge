"""The notification endpoints (SPEC-v2 3.17): list, read, delete, the
channels, and the test notification that goes to the SMTP server."""

import pytest
from clipforge import config, notifications
from fastapi.testclient import TestClient
from smtp_fakes import smtp_server
from sqlalchemy import Engine


def make(engine: Engine, *names: str) -> list[int]:
    ids = []
    for name in names:
        note = notifications.notify(engine, "test", name, f"about {name}", "/x")
        assert note is not None
        ids.append(note.id)
    return ids


def test_notifications_are_listed_newest_first_with_the_unread_count(
    client: TestClient, api_engine: Engine
) -> None:
    make(api_engine, "One", "Two", "Three")

    body = client.get("/api/notifications", params={"limit": 2}).json()

    assert [n["title"] for n in body["items"]] == ["Three", "Two"]
    assert body["unread_count"] == 3
    assert body["items"][0] | {"created_at": None} == {
        "id": 3,
        "kind": "test",
        "title": "Three",
        "body": "about Three",
        "link": "/x",
        "created_at": None,
        "read_at": None,
    }


def test_a_notification_is_read_then_only_the_unread_are_listed(
    client: TestClient, api_engine: Engine
) -> None:
    first, _ = make(api_engine, "One", "Two")

    read = client.post(f"/api/notifications/{first}/read")
    unread = client.get("/api/notifications", params={"unread": True}).json()

    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    assert [n["title"] for n in unread["items"]] == ["Two"]
    assert unread["unread_count"] == 1


def test_read_all_marks_everything_read(client: TestClient, api_engine: Engine) -> None:
    make(api_engine, "One", "Two")

    body = client.post("/api/notifications/read-all").json()

    assert body["unread_count"] == 0
    assert all(n["read_at"] for n in body["items"])


def test_a_notification_is_deleted(client: TestClient, api_engine: Engine) -> None:
    (one,) = make(api_engine, "One")

    assert client.delete(f"/api/notifications/{one}").status_code == 204

    assert client.get("/api/notifications").json()["items"] == []
    for response in (
        client.delete(f"/api/notifications/{one}"),
        client.post(f"/api/notifications/{one}/read"),
    ):
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"


def test_the_limit_is_checked(client: TestClient) -> None:
    assert client.get("/api/notifications", params={"limit": 0}).status_code == 422


def test_email_is_off_in_the_channels_without_smtp_host(client: TestClient) -> None:
    assert client.get("/api/notifications/channels").json() == {
        "email": False,
        "email_to": None,
        "desktop": False,
    }


def test_the_test_notification_is_emailed_when_smtp_is_set(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    with smtp_server() as (port, box):
        cfg = config.settings.model_copy(
            update={
                "smtp_host": "127.0.0.1",
                "smtp_port": port,
                "smtp_from": "cf@example.com",
                "notify_email_to": "me@example.com",
            }
        )
        monkeypatch.setattr(config, "settings", cfg)
        channels = client.get("/api/notifications/channels").json()
        response = client.post("/api/notifications/test")

    assert channels == {"email": True, "email_to": "me@example.com", "desktop": False}
    assert response.status_code == 201
    assert response.json()["title"] == "Test notification"
    (message,) = box.messages
    assert message["Subject"] == "[ClipForge] Test notification"
    assert box.recipients == [["me@example.com"]]
    assert client.get("/api/notifications").json()["unread_count"] == 1
