"""Where a notification goes besides the app (SPEC-v2 3.17): an email through
the owner's SMTP server and an operating-system notification.

Email is on only if SMTP_HOST is set and there is somebody to send to
(email_recipient). Port 465 is implicit TLS; on any other port the
connection is upgraded with STARTTLS if the server offers it. Desktop
notifications are on if desktop_notifications is set: osascript on macOS,
notify-send elsewhere when it is installed.

deliver() never raises: a channel that fails is logged and the others are
still tried.
"""

import logging
import shutil
import smtplib
import ssl
import subprocess
import sys
from email.message import EmailMessage

from clipforge.config import Settings
from clipforge.models import Notification, NotificationChannels

logger = logging.getLogger(__name__)

SMTP_TIMEOUT_S = 10.0
DESKTOP_TIMEOUT_S = 10.0
SMTP_SSL_PORT = 465
APP_NAME = "ClipForge"
# The AppleScript reads the title and text from its arguments, so no quote or
# backslash of theirs can end up in the script.
OSASCRIPT = (
    "on run argv",
    "display notification (item 1 of argv) with title (item 2 of argv)",
    "end run",
)


def email_recipient(cfg: Settings) -> str | None:
    """Return who emails go to: notify_email_to, else smtp_from, else
    smtp_user; None if none of them is set."""
    for candidate in (cfg.notify_email_to, cfg.smtp_from, cfg.smtp_user):
        if candidate.strip():
            return candidate.strip()
    return None


def email_enabled(cfg: Settings) -> bool:
    """Return whether notifications are emailed: smtp_host is set and there is
    a recipient."""
    return bool(cfg.smtp_host.strip()) and email_recipient(cfg) is not None


def channels(cfg: Settings) -> NotificationChannels:
    """Return the channels besides the app that cfg turns on."""
    return NotificationChannels(
        email=email_enabled(cfg),
        email_to=email_recipient(cfg) if email_enabled(cfg) else None,
        desktop=cfg.desktop_notifications,
    )


def _one_line(text: str) -> str:
    """Return text with every run of whitespace as one space (a header may
    not hold a line break)."""
    return " ".join(text.split())


def send_email(cfg: Settings, notification: Notification) -> None:
    """Email notification through the SMTP server of cfg; raises OSError or
    smtplib.SMTPException if it cannot be sent. Does nothing if email is off."""
    recipient = email_recipient(cfg)
    if not email_enabled(cfg) or recipient is None:
        return
    message = EmailMessage()
    message["Subject"] = f"[{APP_NAME}] {_one_line(notification.title)}"
    message["From"] = _one_line(cfg.smtp_from or cfg.smtp_user or recipient)
    message["To"] = _one_line(recipient)
    message.set_content(notification.body or notification.title)
    host, port = cfg.smtp_host.strip(), cfg.smtp_port
    context = ssl.create_default_context()
    if port == SMTP_SSL_PORT:
        client: smtplib.SMTP = smtplib.SMTP_SSL(
            host, port, timeout=SMTP_TIMEOUT_S, context=context
        )
    else:
        client = smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_S)
    with client:
        if port != SMTP_SSL_PORT and client.has_extn("starttls"):
            client.starttls(context=context)
        if cfg.smtp_user:
            client.login(cfg.smtp_user, cfg.smtp_password)
        client.send_message(message)


def desktop_command(notification: Notification) -> list[str] | None:
    """Return the command that shows notification as an operating-system
    notification, None if this system has no program for it."""
    if sys.platform == "darwin":
        script = [arg for line in OSASCRIPT for arg in ("-e", line)]
        return ["osascript", *script, notification.body or " ", notification.title]
    notify_send = shutil.which("notify-send")
    if notify_send is None:
        return None
    return [notify_send, "--app-name", APP_NAME, notification.title, notification.body]


def send_desktop(cfg: Settings, notification: Notification) -> None:
    """Show notification on the desktop if desktop_notifications is on; raises
    OSError or subprocess.SubprocessError if the program fails."""
    if not cfg.desktop_notifications:
        return
    command = desktop_command(notification)
    if command is not None:
        subprocess.run(
            command, check=True, capture_output=True, timeout=DESKTOP_TIMEOUT_S
        )


def deliver(cfg: Settings, notification: Notification) -> None:
    """Send notification to the email and desktop channels that are on; a
    failure of one is logged and never raised."""
    for name, send in (("email", send_email), ("desktop", send_desktop)):
        try:
            send(cfg, notification)
        except (OSError, smtplib.SMTPException, subprocess.SubprocessError):
            logger.exception(
                "could not send notification %d by %s", notification.id, name
            )
