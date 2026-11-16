from pathlib import Path

import pytest
from clipforge.config import RenderSettings, Settings, credit_fields
from pydantic import ValidationError


def test_settings_defaults_match_spec() -> None:
    # Not the owner's .env/.env.local, which may set the model or provider.
    config = Settings(_env_file=None)

    assert config.whisper_model == "small"
    assert config.transcribe_backend == "auto"
    assert config.clip_min_s == 20
    assert config.clip_max_s == 75
    assert config.default_num_clips == 10
    assert config.max_clips_from_llm == 30
    assert config.chunk_minutes == 10
    assert config.chunk_overlap_s == 60
    assert config.laugh_merge_gap_s == 0.75
    assert config.laugh_min_duration_s == 0.4
    assert config.score_weights == {"llm": 0.6, "laugh": 0.25, "energy": 0.15}
    assert config.target_lufs == -14
    assert config.render == RenderSettings(
        fps=30,
        crf=20,
        preset="medium",
        audio_bitrate="160k",
    )
    assert config.llm_provider == "copilot"
    assert config.openai_base_url == "https://api.openai.com/v1"
    assert config.llm_model == "claude-sonnet-5.5"
    assert config.copilot_account == ""
    assert config.ollama_host == "http://localhost:11434"
    assert config.vlm_model == ""
    assert config.frame_caption_interval_s == 10.0
    assert config.data_dir == Path("data")
    assert config.models_dir == Path("models")
    assert "{channel}" in config.credit_template


def test_missing_yaml_uses_code_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    assert Settings().clip_min_s == 20


def test_yaml_and_environment_overrides(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "config.yaml").write_text(
        "clip_min_s: 25\nllm_provider: openai\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    assert Settings().clip_min_s == 25

    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert Settings().llm_provider == "ollama"


@pytest.mark.parametrize(
    ("template", "fields"),
    [
        ("Credit: {channel}", ["channel"]),
        ("{title} by {channel} ({channel_url})", ["title", "channel", "channel_url"]),
        ("{{channel}} stays {channel}", ["channel"]),
        ("Clipped with ClipForge", []),
        ("", []),
    ],
)
def test_credit_template_may_use_the_credit_fields(
    template: str, fields: list[str]
) -> None:
    assert credit_fields(template) == fields
    assert Settings(credit_template=template).credit_template == template


@pytest.mark.parametrize(
    ("template", "error"),
    [
        ("{}", "may only use"),
        ("{0}", "may only use"),
        ("Credit: {uploader}", "may only use"),
        ("{channel!r}", "may only use"),
        ("{channel:>10}", "may only use"),
        ("{channel:{title}}", "may only use"),
        ("{channel.upper}", "may only use"),
        ("{channel[0]}", "may only use"),
        ("Credit: {channel", "is not valid: expected '}'"),
        ("Credit: channel}", "is not valid: Single '}'"),
    ],
)
def test_credit_template_rejects_other_fields_and_bad_braces(
    template: str, error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        credit_fields(template)
    with pytest.raises(ValidationError, match=error):
        Settings(credit_template=template)


def test_env_example_has_configured_environment_keys() -> None:
    env_file = Path(".env.example").read_text(encoding="utf-8")
    keys = {
        line.partition("=")[0]
        for line in env_file.splitlines()
        if not line.startswith("#")
    }

    assert keys == {
        "LLM_PROVIDER",
        "GITHUB_COPILOT_TOKEN",
        "COPILOT_ACCOUNT",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
        "CLAUDE_CODE_BIN",
        "CLAUDE_CODE_MODEL",
        "DEEP_FILTER_BIN",
        "PIPER_BIN",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "LLM_MODEL",
        "OLLAMA_HOST",
        "VLM_MODEL",
        "HF_TOKEN",
        "FFMPEG_BIN",
        "FFPROBE_BIN",
        "VIDEO_ENCODER",
        "YTDLP_COOKIES_FROM_BROWSER",
        "YTDLP_COOKIES_FILE",
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
        "YOUTUBE_API_KEY",
        "TWITCH_CLIENT_ID",
        "TWITCH_CLIENT_SECRET",
    }


def test_dotenv_local_overrides_and_yaml_has_no_secrets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    yaml_text = Path("config.yaml").read_text(encoding="utf-8")
    for secret in ("openai_api_key", "github_copilot_token", "hf_token"):
        assert secret not in yaml_text

    (tmp_path / ".env").write_text("LLM_MODEL=from-env\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("LLM_MODEL=from-local\n", encoding="utf-8")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)
    assert Settings().llm_model == "from-local"
