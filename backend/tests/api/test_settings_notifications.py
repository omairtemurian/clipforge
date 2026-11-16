"""The notification settings of the Settings API (SPEC-v2 3.17): SMTP, the
desktop channel and the quota warning, with the SMTP password kept secret."""

from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge import config
from fastapi.testclient import TestClient

PASSWORD = "smtp-secret-pw"


@pytest.fixture
def env_file(work_in_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The .env.local that the API writes, with the test-only environment
    overrides of the notification channels removed so that it can change."""
    monkeypatch.delenv("SMTP_HOST")
    monkeypatch.delenv("DESKTOP_NOTIFICATIONS")
    return work_in_tmp / ".env.local"


def test_get_shows_the_notification_settings_without_the_password(
    client: TestClient,
) -> None:
    config.settings = config.Settings(
        data_dir=config.settings.data_dir,
        smtp_host="mail.example",
        smtp_password=PASSWORD,
    )

    response = client.get("/api/settings")

    body = response.json()
    assert body["smtp_host"] == "mail.example"
    assert body["smtp_port"] == 587
    assert body["smtp_password_set"] is True
    assert body["desktop_notifications"] is False
    assert body["quota_warn_percent"] == 80
    assert body["digest_time"] == "08:00"
    assert PASSWORD not in response.text
    assert "smtp_password" not in body


def test_put_saves_the_notification_settings(
    client: TestClient, env_file: Path
) -> None:
    response = client.put(
        "/api/settings",
        json={
            "smtp_host": "mail.example",
            "smtp_port": 465,
            "smtp_user": "me",
            "smtp_password": PASSWORD,
            "smtp_from": "clipforge@example.com",
            "notify_email_to": "me@example.com",
            "desktop_notifications": True,
            "quota_warn_percent": 90,
            "digest_time": "07:45",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["smtp_host"] == "mail.example" and body["smtp_port"] == 465
    assert body["smtp_password_set"] is True
    assert body["desktop_notifications"] is True
    assert PASSWORD not in response.text
    saved = config.settings
    assert saved.smtp_password == PASSWORD
    assert saved.notify_email_to == "me@example.com"
    assert saved.quota_warn_percent == 90
    assert saved.digest_time == "07:45"
    assert "SMTP_PASSWORD=" in env_file.read_text()
    channels = client.get("/api/notifications/channels").json()
    assert channels == {"email": True, "email_to": "me@example.com", "desktop": True}


def test_an_empty_host_turns_email_off_and_the_password_can_be_cleared(
    client: TestClient, env_file: Path
) -> None:
    client.put(
        "/api/settings", json={"smtp_host": "mail.example", "smtp_password": PASSWORD}
    )

    body = client.put(
        "/api/settings", json={"smtp_host": "", "smtp_password": ""}
    ).json()

    assert body["smtp_host"] == "" and body["smtp_password_set"] is False
    assert client.get("/api/notifications/channels").json()["email"] is False


@pytest.mark.parametrize(
    "change",
    [
        {"smtp_port": 0},
        {"smtp_port": 70000},
        {"quota_warn_percent": 0},
        {"quota_warn_percent": 100},
        {"digest_time": "8am"},
        {"digest_time": "24:00"},
        {"smtp_host": "a\nb"},
    ],
)
def test_invalid_notification_settings_are_refused(
    client: TestClient, env_file: Path, change: dict[str, object]
) -> None:
    response = client.put("/api/settings", json=change)

    assert_error(response, 422, "validation_error")
    assert not env_file.exists()


def test_an_empty_digest_time_turns_the_daily_digest_off(
    client: TestClient, env_file: Path
) -> None:
    body = client.put("/api/settings", json={"digest_time": ""}).json()

    assert body["digest_time"] == ""
    assert config.settings.digest_time == ""
