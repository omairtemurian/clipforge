"""Report which v2 credentials are set, by name only (never the value).

A credential is present when its environment variable, or its entry in .env
or .env.local, is not empty. Exits 0 either way: a missing credential blocks
a live feature, not the build (docs/questions.md):

    uv run python scripts/check_prereqs.py
"""

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ENV_FILES = (".env", ".env.local")

CREDENTIALS = (
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "TIKTOK_CLIENT_KEY",
    "TIKTOK_CLIENT_SECRET",
    "META_APP_ID",
    "META_APP_SECRET",
    "META_LOGIN_CONFIG_ID",
    "X_CLIENT_ID",
    "X_CLIENT_SECRET",
    "LINKEDIN_CLIENT_ID",
    "LINKEDIN_CLIENT_SECRET",
    "PEXELS_API_KEY",
    "PIXABAY_API_KEY",
    "FREESOUND_API_KEY",
    "DROPBOX_APP_KEY",
    "DROPBOX_APP_SECRET",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "HF_TOKEN",
    "YOUTUBE_API_KEY",
    "TWITCH_CLIENT_ID",
    "TWITCH_CLIENT_SECRET",
)


def load_values(root: Path, environ: Mapping[str, str]) -> dict[str, str]:
    """Merge the env files of root with environ; environ wins."""
    values: dict[str, str] = {}
    for name in ENV_FILES:
        path = root / name
        if path.is_file():
            values.update({k: v for k, v in dotenv_values(path).items() if v})
    values.update({k: v for k, v in environ.items() if v})
    return values


def status_lines(values: Mapping[str, str]) -> list[str]:
    """One "NAME: present|missing" line per credential."""
    return [
        f"{name}: {'present' if values.get(name) else 'missing'}"
        for name in CREDENTIALS
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Print the status of every credential and return 0."""
    lines = status_lines(load_values(ROOT, os.environ))
    print("\n".join(lines))
    missing = sum(line.endswith("missing") for line in lines)
    print(f"{len(lines) - missing} present, {missing} missing")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
