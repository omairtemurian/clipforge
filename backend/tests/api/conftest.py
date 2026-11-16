"""Fixtures of the API tests: apps on a temporary data directory."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from clipforge.api.app import create_app
from fastapi.testclient import TestClient
from sqlalchemy import Engine

ENV_SETTINGS = (
    "LLM_PROVIDER",
    "LLM_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OLLAMA_HOST",
    "GITHUB_COPILOT_TOKEN",
    "COPILOT_ACCOUNT",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL",
    "CLAUDE_CODE_BIN",
    "CLAUDE_CODE_MODEL",
    "WHISPER_MODEL",
    "CREDIT_TEMPLATE",
    "MODELS_DIR",
    "FFMPEG_BIN",
    "FFPROBE_BIN",
    "VIDEO_ENCODER",
    "YTDLP_COOKIES_FROM_BROWSER",
    "YTDLP_COOKIES_FILE",
    "USAGE_CAP_COMPUTE_HOURS",
    "USAGE_CAP_LLM_TOKENS",
    "USAGE_CAP_API_CALLS",
    "INBOX_DIR",
    "INBOX_POLL_S",
    "AUTO_IMPORT_POLL_S",
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "DROPBOX_APP_KEY",
    "DROPBOX_APP_SECRET",
    "TIKTOK_CLIENT_KEY",
    "TIKTOK_CLIENT_SECRET",
    "META_APP_ID",
    "META_APP_SECRET",
    "META_LOGIN_CONFIG_ID",
    "PUBLIC_CALLBACK_URL",
    "YOUTUBE_API_KEY",
    "FREESOUND_API_KEY",
    "TWITCH_CLIENT_ID",
    "TWITCH_CLIENT_SECRET",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_PASSWORD",
    "SMTP_FROM",
    "NOTIFY_EMAIL_TO",
    "QUOTA_WARN_PERCENT",
)


@pytest.fixture(autouse=True)
def work_in_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run in an empty directory: Settings reads .env.local and config.yaml
    from the working directory and the Settings API writes .env.local there,
    so the owner's real files are never read or changed. Environment
    variables of the editable settings are dropped for the same reason."""
    for key in ENV_SETTINGS:
        monkeypatch.delenv(key, raising=False)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    return cwd


@pytest.fixture
def client(data_dir: Path) -> Iterator[TestClient]:
    """A client of an app whose job worker is off, so jobs stay queued, and
    that does not draw the caption previews at startup."""
    app = create_app(run_worker=False, caption_previews=False)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def api_engine(client: TestClient) -> Engine:
    """The engine of the app under test."""
    engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
    return engine
