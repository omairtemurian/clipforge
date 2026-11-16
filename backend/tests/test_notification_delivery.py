"""The email and desktop channels of the notifications (SPEC-v2 3.17): email
goes to a real SMTP conversation on localhost (smtp_fakes) and is off without
SMTP_HOST; the desktop commands are checked, and never run."""

import smtplib
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any

import pytest
from clipforge import config, notification_delivery
from clipforge.config import Settings
from clipforge.models import Notification
from clipforge.notification_delivery import (
    channels,
    deliver,
    desktop_command,
    email_enabled,
    email_recipient,
    send_email,
)
from smtp_fakes import smtp_server

NOW = datetime(2030, 1, 15, 9, 0, tzinfo=UTC)
NOTE = Notification(
    id=1,
    kind="project_done",
    title="Talk is ready",
    body="3 clips found.",
    link="/projects/1",
    created_at=NOW,
    read_at=None,
)


def settings(**changes: Any) -> Settings:
    return config.settings.model_copy(update=changes)


def test_email_is_off_without_smtp_host() -> None:
    cfg = settings(smtp_host="", smtp_from="me@example.com")

    assert not email_enabled(cfg)
    assert channels(cfg).email is False
    assert channels(cfg).email_to is None
    send_email(cfg, NOTE)


def test_email_needs_somebody_to_send_to() -> None:
    assert not email_enabled(settings(smtp_host="localhost"))
    assert email_recipient(settings(smtp_user="u@example.com")) == "u@example.com"
    cfg = settings(
        smtp_host="localhost", smtp_from="from@x.io", notify_email_to=" to@x.io "
    )
    assert email_recipient(cfg) == "to@x.io"
    assert channels(cfg).email_to == "to@x.io"


def test_a_notification_is_emailed_to_the_smtp_server() -> None:
    with smtp_server() as (port, box):
        cfg = settings(
            smtp_host="127.0.0.1",
            smtp_port=port,
            smtp_from="clipforge@example.com",
            notify_email_to="owner@example.com",
        )
        send_email(cfg, NOTE)

    (message,) = box.messages
    assert message["Subject"] == "[ClipForge] Talk is ready"
    assert message["From"] == "clipforge@example.com"
    assert message["To"] == "owner@example.com"
    assert str(message.get_payload()).strip() == "3 clips found."
    assert box.recipients == [["owner@example.com"]]
    assert box.logins == []


def test_smtp_user_and_password_log_in_and_a_title_stays_one_line() -> None:
    note = NOTE.model_copy(update={"title": "Two\r\nBcc: spy@example.com"})
    with smtp_server(auth=True) as (port, box):
        cfg = settings(
            smtp_host="127.0.0.1",
            smtp_port=port,
            smtp_user="user@example.com",
            smtp_password="s3cret",
        )
        send_email(cfg, note)

    assert box.logins == [("user@example.com", "s3cret")]
    (message,) = box.messages
    assert message["Subject"] == "[ClipForge] Two Bcc: spy@example.com"
    assert message["Bcc"] is None
    assert message["From"] == message["To"] == "user@example.com"


def test_a_server_that_is_down_is_logged_and_never_raised(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with smtp_server() as (port, _):
        pass
    cfg = settings(smtp_host="127.0.0.1", smtp_port=port, smtp_from="a@example.com")

    with pytest.raises(OSError):
        send_email(cfg, NOTE)
    deliver(cfg, NOTE)

    assert "could not send notification 1 by email" in caplog.text


def test_port_465_uses_implicit_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    used: list[str] = []

    class Ssl:
        def __init__(self, host: str, port: int, **kwargs: Any) -> None:
            used.append(f"ssl {host}:{port}")
            raise smtplib.SMTPConnectError(421, "stop here")

    monkeypatch.setattr(smtplib, "SMTP_SSL", Ssl)
    cfg = settings(smtp_host="mail.example.com", smtp_port=465, smtp_from="a@x.io")

    with pytest.raises(smtplib.SMTPConnectError):
        send_email(cfg, NOTE)

    assert used == ["ssl mail.example.com:465"]


def test_an_empty_smtp_port_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_PORT", "")

    assert Settings().smtp_port == 587
    assert Settings(smtp_port=2525).smtp_port == 2525


def test_the_desktop_notification_is_off_unless_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", lambda cmd, **_: ran.append(cmd))

    deliver(settings(desktop_notifications=False), NOTE)
    assert ran == []

    deliver(settings(desktop_notifications=True), NOTE)
    assert len(ran) == (1 if desktop_command(NOTE) else 0)


@pytest.mark.skipif(sys.platform != "darwin", reason="osascript is macOS only")
def test_the_macos_command_passes_text_as_arguments_not_script() -> None:
    note = NOTE.model_copy(update={"title": 'Say "hi"', "body": "a \\ b"})

    command = desktop_command(note)

    assert command is not None
    assert command[0] == "osascript"
    assert command[-2:] == ["a \\ b", 'Say "hi"']
    assert all('"hi"' not in part for part in command[1:-2])


def test_the_linux_command_is_none_without_notify_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(notification_delivery.sys, "platform", "linux")
    monkeypatch.setattr(notification_delivery.shutil, "which", lambda _: None)
    assert desktop_command(NOTE) is None

    monkeypatch.setattr(notification_delivery.shutil, "which", lambda _: "/usr/bin/ns")
    assert desktop_command(NOTE) == [
        "/usr/bin/ns",
        "--app-name",
        "ClipForge",
        "Talk is ready",
        "3 clips found.",
    ]


def test_a_failing_desktop_program_is_logged_and_never_raised(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*_: Any, **__: Any) -> None:
        raise subprocess.CalledProcessError(1, "osascript")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(notification_delivery, "desktop_command", lambda _: ["x"])

    deliver(settings(desktop_notifications=True), NOTE)

    assert "by desktop" in caplog.text
