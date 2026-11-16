"""The settings that the Settings page edits (SPEC 8.7, PRD 11).

SettingsView is what GET /api/settings shows: API keys are never sent, only
whether one is set. SettingsUpdate is the PUT body, in which an absent (or
null) field keeps its value and an empty key clears it. save_settings writes
the changes to .env.local, which Settings reads after the environment and
before config.yaml, and then swaps config.settings, so the next job or LLM
request uses them. data_dir is shown but cannot be changed here: the open
database is in it, so changing it takes a restart.
"""

import json
import re
import shutil
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeFloat,
    StringConstraints,
    ValidationError,
)

from clipforge import config, encoders
from clipforge.config import (
    LlmProvider,
    PostMissedPolicy,
    Settings,
    TranscribeBackend,
)
from clipforge.encoders import VideoEncoder
from clipforge.env_file import restore_env_file, update_env_file
from clipforge.pipeline.transcribe_mlx import Backend, choose_backend
from clipforge.pipeline.ytdlp_session import parse_browser
from clipforge.required_tags import clean_tags

# Where the Settings page saves: the last env_file of Settings, as the
# relative path that Settings itself reads (from the working directory).
ENV_LOCAL = Path(".env.local")
SECRET_FIELDS = (
    "openai_api_key",
    "github_copilot_token",
    "anthropic_api_key",
    "smtp_password",
)


class SettingsInvalid(ValueError):
    """A change that Settings would not accept; the message lists the problems."""


class SettingsConflict(RuntimeError):
    """A change that cannot take effect because something else sets the value."""


def _http_url(url: str) -> str:
    """Require an http(s) URL."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("must be an http(s) URL")
    return url


def _tool(name: str) -> str:
    """Accept an empty name (use the default) or an executable that exists."""
    if name and shutil.which(name) is None:
        raise ValueError(f"{name!r} is not an executable file or a tool on PATH")
    return name


def _browser(spec: str) -> str:
    """Accept an empty spec (no cookies) or "browser[:profile]" that yt-dlp
    can read cookies from."""
    parse_browser(spec)
    return spec


def _encoder(encoder: VideoEncoder) -> VideoEncoder:
    """Accept an encoder that the ffmpeg in use has."""
    if encoder not in encoders.available_encoders(config.settings.ffmpeg_bin):
        raise ValueError(f"ffmpeg {config.settings.ffmpeg_bin} has no {encoder}")
    return encoder


def _account(login: str) -> str:
    """Require a GitHub account name: letters, digits, - and _, not starting
    with - (it is an argument of `gh auth token -u`); empty: gh's active
    account."""
    if login and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", login):
        raise ValueError("must be a GitHub account name")
    return login


def _cookies_file(path: str) -> str:
    """Accept an empty path (no cookies file) or a file that exists."""
    if path and not Path(path).expanduser().is_file():
        raise ValueError(f"{path!r} is not a file")
    return path


# One line without surrounding blanks: a .env value cannot span lines.
Line = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[^\r\n]*$")]
Name = Annotated[Line, StringConstraints(min_length=1)]
Url = Annotated[Name, AfterValidator(_http_url)]
Tool = Annotated[Line, AfterValidator(_tool)]
Program = Annotated[Name, AfterValidator(_tool)]
Browser = Annotated[Line, AfterValidator(_browser)]
CookiesFile = Annotated[Line, AfterValidator(_cookies_file)]
Account = Annotated[Line, AfterValidator(_account)]
Encoder = Annotated[VideoEncoder, AfterValidator(_encoder)]
Hashtags = Annotated[list[str], AfterValidator(clean_tags), Field(max_length=30)]
Port = Annotated[int, Field(ge=1, le=65535)]
WarnPercent = Annotated[float, Field(gt=0, lt=100)]
DigestTime = Annotated[str, Field(pattern=r"^(([01]\d|2[0-3]):[0-5]\d)?$")]


class SettingsView(BaseModel):
    """The settings as GET /api/settings returns them."""

    llm_provider: LlmProvider
    llm_model: str
    openai_base_url: str
    ollama_host: str
    openai_api_key_set: bool
    github_copilot_token_set: bool
    copilot_account: str
    anthropic_api_key_set: bool
    anthropic_base_url: str
    anthropic_model: str
    claude_code_bin: str
    claude_code_model: str
    whisper_model: str
    # What transcribes: the setting, and the backend it picks on this machine.
    transcribe_backend: TranscribeBackend
    transcribe_backend_active: Backend
    credit_template: str
    always_hashtags: list[str]
    # Posts due while the app was off: posted late on start, or skipped.
    post_missed_policy: PostMissedPolicy
    models_dir: str
    ffmpeg_bin: str
    ffprobe_bin: str
    # The H.264 encoder of renders and the ones this ffmpeg has.
    video_encoder: VideoEncoder
    video_encoders: list[VideoEncoder]
    ytdlp_cookies_from_browser: str
    ytdlp_cookies_file: str
    usage_cap_compute_hours: float
    usage_cap_llm_tokens: float
    usage_cap_api_calls: float
    # Notifications (SPEC-v2 3.17): email is on only with an smtp_host.
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password_set: bool
    smtp_from: str
    notify_email_to: str
    desktop_notifications: bool
    quota_warn_percent: float
    digest_time: str
    data_dir: str


class SettingsUpdate(BaseModel):
    """The PUT body: the settings to change. An empty ffmpeg_bin or
    ffprobe_bin means the default tool; an empty key, browser or cookies
    file clears it; always_hashtags [] clears them. A usage cap of 0 means
    no cap. video_encoder must be one that ffmpeg has. An empty smtp_host
    turns email notifications off, an empty digest_time the daily digest."""

    model_config = ConfigDict(extra="forbid")

    llm_provider: LlmProvider | None = None
    llm_model: Name | None = None
    openai_base_url: Url | None = None
    ollama_host: Url | None = None
    openai_api_key: Line | None = None
    github_copilot_token: Line | None = None
    copilot_account: Account | None = None
    anthropic_api_key: Line | None = None
    anthropic_base_url: Url | None = None
    anthropic_model: Name | None = None
    claude_code_bin: Program | None = None
    claude_code_model: Name | None = None
    whisper_model: Name | None = None
    transcribe_backend: TranscribeBackend | None = None
    credit_template: Name | None = None
    always_hashtags: Hashtags | None = None
    post_missed_policy: PostMissedPolicy | None = None
    models_dir: Name | None = None
    ffmpeg_bin: Tool | None = None
    ffprobe_bin: Tool | None = None
    video_encoder: Encoder | None = None
    ytdlp_cookies_from_browser: Browser | None = None
    ytdlp_cookies_file: CookiesFile | None = None
    usage_cap_compute_hours: NonNegativeFloat | None = None
    usage_cap_llm_tokens: NonNegativeFloat | None = None
    usage_cap_api_calls: NonNegativeFloat | None = None
    smtp_host: Line | None = None
    smtp_port: Port | None = None
    smtp_user: Line | None = None
    smtp_password: Line | None = None
    smtp_from: Line | None = None
    notify_email_to: Line | None = None
    desktop_notifications: bool | None = None
    quota_warn_percent: WarnPercent | None = None
    digest_time: DigestTime | None = None

    def changes(self) -> dict[str, str]:
        """Return the fields that this update sets, by name."""
        return {
            name: json.dumps(value) if isinstance(value, list) else str(value)
            for name, value in self.model_dump().items()
            if value is not None
        }


def settings_view(cfg: Settings) -> SettingsView:
    """Return cfg as the Settings page shows it."""
    return SettingsView(
        llm_provider=cfg.llm_provider,
        llm_model=cfg.llm_model,
        openai_base_url=cfg.openai_base_url,
        ollama_host=cfg.ollama_host,
        openai_api_key_set=bool(cfg.openai_api_key),
        github_copilot_token_set=bool(cfg.github_copilot_token),
        copilot_account=cfg.copilot_account,
        anthropic_api_key_set=bool(cfg.anthropic_api_key),
        anthropic_base_url=cfg.anthropic_base_url,
        anthropic_model=cfg.anthropic_model,
        claude_code_bin=cfg.claude_code_bin,
        claude_code_model=cfg.claude_code_model,
        whisper_model=cfg.whisper_model,
        transcribe_backend=cfg.transcribe_backend,
        transcribe_backend_active=choose_backend(cfg)[0],
        credit_template=cfg.credit_template,
        always_hashtags=cfg.always_hashtags,
        post_missed_policy=cfg.post_missed_policy,
        models_dir=str(cfg.models_dir),
        ffmpeg_bin=cfg.ffmpeg_bin,
        ffprobe_bin=cfg.ffprobe_bin,
        video_encoder=cfg.video_encoder,
        video_encoders=list(encoders.available_encoders(cfg.ffmpeg_bin)),
        ytdlp_cookies_from_browser=cfg.ytdlp_cookies_from_browser,
        ytdlp_cookies_file=cfg.ytdlp_cookies_file,
        usage_cap_compute_hours=cfg.usage_cap_compute_hours,
        usage_cap_llm_tokens=cfg.usage_cap_llm_tokens,
        usage_cap_api_calls=cfg.usage_cap_api_calls,
        smtp_host=cfg.smtp_host,
        smtp_port=cfg.smtp_port,
        smtp_user=cfg.smtp_user,
        smtp_password_set=bool(cfg.smtp_password),
        smtp_from=cfg.smtp_from,
        notify_email_to=cfg.notify_email_to,
        desktop_notifications=cfg.desktop_notifications,
        quota_warn_percent=cfg.quota_warn_percent,
        digest_time=cfg.digest_time,
        data_dir=str(cfg.data_dir),
    )


def with_changes(changes: dict[str, str]) -> Settings:
    """Return the current settings with changes applied (nothing is saved).

    Raises SettingsInvalid if Settings rejects the result, for example a
    credit_template that uses a field it does not know.
    """
    fields: dict[str, Any] = {"data_dir": config.settings.data_dir, **changes}
    try:
        return Settings(**fields)
    except ValidationError as exc:
        raise SettingsInvalid(_problems(exc)) from exc


def save_settings(update: SettingsUpdate) -> Settings:
    """Save update in .env.local, make it the app's settings and return them.

    The file is put back as it was, and SettingsInvalid or SettingsConflict
    raised, if the saved values do not read back as given: an environment
    variable of the same name wins over .env.local.
    """
    changes = update.changes()
    expected = with_changes(changes)
    if not changes:
        return config.settings
    previous = update_env_file(
        ENV_LOCAL, {name.upper(): value for name, value in changes.items()}
    )
    try:
        saved = with_changes({})
    except SettingsInvalid:
        restore_env_file(ENV_LOCAL, previous)
        raise
    shadowed = [n for n in changes if getattr(saved, n) != getattr(expected, n)]
    if shadowed:
        restore_env_file(ENV_LOCAL, previous)
        names = ", ".join(shadowed)
        raise SettingsConflict(
            f"{names} cannot be changed here: an environment variable sets it"
        )
    config.settings = saved
    return saved


def _problems(exc: ValidationError) -> str:
    """Return one line per problem of exc: "credit_template: ...". The input
    values are left out, as they may be keys."""
    return "; ".join(
        f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in exc.errors()
    )
