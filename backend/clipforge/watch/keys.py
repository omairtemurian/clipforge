"""The watch's signing secrets.

One random master key lives in data_dir (watch_secret.key, mode 0600, made
on first use). The secret of each WebSub topic and of the Twitch EventSub
subscriptions is an HMAC of the master key and a purpose string, so no
secret is stored in a database row and each topic gets its own.
"""

import hashlib
import hmac
import os
import secrets
import threading
from pathlib import Path

from clipforge import config

KEY_FILE = "watch_secret.key"
_lock = threading.Lock()


def master_key(data_dir: Path | None = None) -> bytes:
    """Return the master key of data_dir (the configured one by default),
    making it if there is none."""
    directory = data_dir or config.settings.data_dir
    path = directory / KEY_FILE
    with _lock:
        if not path.is_file():
            directory.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="ascii") as file:
                file.write(secrets.token_hex(32))
        return bytes.fromhex(path.read_text(encoding="ascii").strip())


def derived_secret(purpose: str, data_dir: Path | None = None) -> str:
    """Return the secret for purpose: 64 hex characters (WebSub wants less
    than 200 bytes, Twitch 10 to 100 ASCII characters)."""
    key = master_key(data_dir)
    return hmac.new(key, purpose.encode(), hashlib.sha256).hexdigest()
