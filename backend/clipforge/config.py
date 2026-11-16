import string
from pathlib import Path
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    NonNegativeFloat,
    PositiveFloat,
    PositiveInt,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

from clipforge import encoders
from clipforge.encoders import SOFTWARE, VideoEncoder
from clipforge.proedit.config import ProEditConfig
from clipforge.required_tags import clean_tags, tags_from_text
from clipforge.zoom_out_settings import ZoomOutSettings

# The keg-only Homebrew formula that bundles libass, which plain ffmpeg lacks.
FFMPEG_FULL_BIN_DIR = Path("/opt/homebrew/opt/ffmpeg-full/bin")

LlmProvider = Literal["copilot", "openai", "ollama", "anthropic", "claude_code"]
# What transcribes: faster-whisper (CPU) or MLX Whisper (Apple GPU); auto is
# MLX on Apple Silicon when mlx-whisper and its model are there.
TranscribeBackend = Literal["auto", "faster_whisper", "mlx"]
# What the posting worker does on start with the posts that came due while
# the app was off: publish them late, or skip them (status skipped).
PostMissedPolicy = Literal["post_late", "skip"]
# The GitHub CLI account whose token Copilot uses; empty: gh's active account.
DEFAULT_COPILOT_ACCOUNT = ""

# The fields that credit_template may use, from the source's meta.json.
CREDIT_FIELDS = ("channel", "channel_url", "title")


def credit_fields(template: str) -> list[str]:
    """Return the fields that template, a credit_template, uses, in order.

    A field is one of CREDIT_FIELDS in braces, such as {channel}, with no
    conversion or format spec; {{ and }} are literal braces. Raises
    ValueError if template is not a valid format string or uses anything else.
    """
    fields: list[str] = []
    try:
        parts = list(string.Formatter().parse(template))
    except ValueError as exc:
        raise ValueError(f"credit_template {template!r} is not valid: {exc}") from exc
    for _, name, spec, conversion in parts:
        if name is None:
            continue
        if name not in CREDIT_FIELDS or spec or conversion:
            known = ", ".join(f"{{{field}}}" for field in CREDIT_FIELDS)
            raise ValueError(f"credit_template may only use {known}, not {name!r}")
        fields.append(name)
    return fields


def default_tool(name: str) -> str:
    """Return the path of ffmpeg-full's `name` binary if it is installed, else
    the bare `name`, which is looked up on PATH."""
    full = FFMPEG_FULL_BIN_DIR / name
    return str(full) if full.is_file() else name


class RenderSettings(BaseModel):
    fps: int = 30
    crf: int = 20
    preset: str = "medium"
    audio_bitrate: str = "160k"
    # The H.264 encoder (clipforge.encoders); Settings.video_encoder by default.
    encoder: VideoEncoder = SOFTWARE


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        case_sensitive=False,
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    whisper_model: str = "small"
    transcribe_backend: TranscribeBackend = "auto"
    clip_min_s: int = 20
    clip_max_s: int = 75
    default_num_clips: int = 10
    max_clips_from_llm: int = 30
    chunk_minutes: int = 10
    chunk_overlap_s: int = 60
    laugh_merge_gap_s: float = 0.75
    laugh_min_duration_s: float = 0.4
    score_weights: dict[str, float] = {
        "llm": 0.6,
        "laugh": 0.25,
        "energy": 0.15,
    }
    # The share of the whole run that each step of a job takes, for the
    # overall progress and ETA (job_progress); only the ratios matter.
    step_weights: dict[str, float] = {
        "ingest": 10,
        "transcribe": 25,
        "signals": 5,
        "visuals": 3,
        "enrich": 1,
        "curate": 10,
        "score": 1,
        "snap": 1,
        "reframe": 10,
        "render": 34,
        "plan": 10,
        "proxy": 15,
        "critic": 30,
        "final": 45,
    }
    target_lufs: int = -14
    render: RenderSettings = RenderSettings()
    # Auto zoom-out moments (pipeline/layout_auto, zoom_out_settings).
    zoom_out: ZoomOutSettings = ZoomOutSettings()

    llm_provider: LlmProvider = "copilot"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "claude-sonnet-5.5"
    ollama_host: str = "http://localhost:11434"
    # The Ollama vision model that captions frames (engines/vlm_ollama);
    # empty: the first model with the vision capability that `ollama list`
    # shows. A frame is captioned at every scene cut and every
    # frame_caption_interval_s seconds (pipeline/frame_captions).
    vlm_model: str = ""
    frame_caption_interval_s: PositiveFloat = 10.0
    github_copilot_token: str = ""
    # Without github_copilot_token, Copilot uses this GitHub CLI account's
    # token (`gh auth token -u <account>`).
    copilot_account: str = DEFAULT_COPILOT_ACCOUNT
    # LLM_PROVIDER=anthropic: Anthropic's API with an API key; the model ids
    # are Anthropic's (docs/decisions.md "TASK-13 anthropic provider").
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-sonnet-5-5"
    # LLM_PROVIDER=claude_code: the Claude subscription through the Claude
    # Code CLI (`claude -p`); the model is an alias (sonnet, opus) or full id.
    claude_code_bin: str = "claude"
    claude_code_model: str = "sonnet"
    # The deep-filter program of the DeepFilterNet engine; empty: the one in
    # models/deepfilternet, else `deep-filter` on PATH (engines/deepfilternet).
    deep_filter_bin: str = ""
    # The piper program of the Piper voiceover engine; empty: `piper` on PATH
    # (engines/tts).
    piper_bin: str = ""
    hf_token: str = ""
    data_dir: Path = Path("data")
    models_dir: Path = Path("models")
    credit_template: str = "Credit: {channel}"
    # Hashtags (without "#") that every generated post text carries, besides
    # a social account's own and the campaign's (required_tags).
    always_hashtags: list[str] = []
    ffmpeg_bin: str = ""
    ffprobe_bin: str = ""
    # The H.264 encoder of renders; unset: h264_videotoolbox if ffmpeg has it.
    video_encoder: VideoEncoder = SOFTWARE
    # yt-dlp reads cookies from this browser ("chrome", or "chrome:Profile 1"
    # for a profile) and/or a Netscape cookies.txt, for sign-in-only videos.
    ytdlp_cookies_from_browser: str = ""
    ytdlp_cookies_file: str = ""
    # The job worker pool (SPEC-v2 2.2): `workers` threads run queued jobs;
    # job_concurrency caps the running jobs of a kind (a kind not listed is
    # capped only by workers); the gpu_job_kinds share one lock, so at most
    # one job of all of them runs at a time.
    workers: PositiveInt = 2
    job_concurrency: dict[str, PositiveInt] = {
        "process": 1,
        "render": 2,
        "reprompt": 1,
        "proedit": 1,
    }
    gpu_job_kinds: list[str] = ["process", "reprompt"]
    # The inbox folder watch (SPEC-v2 3.1): a video file that appears in
    # inbox_dir (empty: no watch) becomes a project once its size and
    # modification time are unchanged across two polls, inbox_poll_s apart.
    inbox_dir: str = ""
    inbox_poll_s: PositiveFloat = 10.0
    # Auto Import (SPEC-v2 3.1) reads the RSS feed of each watched YouTube
    # channel, and asks Twitch whether each watched streamer is live, about
    # every auto_import_poll_s seconds (at least 30; jittered, backed off
    # after errors). A source with a verified push subscription is polled
    # only every 15 min, as a safety net.
    auto_import_poll_s: float = Field(default=60.0, ge=30)
    # The public HTTPS URL that forwards to this app's API (e.g. a tunnel):
    # with it the watch subscribes to WebSub (YouTube) and EventSub (Twitch)
    # pushes; empty: polling only.
    public_callback_url: str = ""
    # The YouTube Data API key that resolves @handles to channel ids.
    youtube_api_key: str = ""
    # The stock B-roll API keys (SPEC-v2 3.6); a provider without its key is
    # disabled and says so.
    pexels_api_key: str = ""
    pixabay_api_key: str = ""
    # The Freesound API key (token) of the Pro Edit audio library (SPEC-v3
    # 5.1); without it the library says "Add a Freesound key".
    freesound_api_key: str = ""
    # The Twitch app (client credentials) of the go-live watch.
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    # The Google OAuth app (a "Desktop app" client) of the Google Drive
    # import; without the client id Drive shows "needs credentials".
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    # The Dropbox app of the optional Dropbox import (PKCE: the app secret is
    # not used); without the app key Dropbox shows "needs credentials".
    dropbox_app_key: str = ""
    dropbox_app_secret: str = ""
    # The YouTube publisher uses the same Google OAuth app. Its Google Cloud
    # project's daily YouTube Data API quotas (reset at midnight Pacific
    # Time): videos.insert calls, and units of every other method combined.
    youtube_daily_uploads: PositiveInt = 100
    youtube_daily_quota_units: PositiveInt = 10_000
    # The TikTok app (Login Kit for Desktop + Content Posting API, Direct
    # Post) of the TikTok publisher; without the client key TikTok shows
    # "needs credentials".
    tiktok_client_key: str = ""
    tiktok_client_secret: str = ""
    # The Meta app (Facebook Login for Business + Instagram Graph API) of
    # the Instagram publisher; without its id and secret Instagram shows
    # "needs credentials". The optional login configuration id is sent as
    # config_id when the app's Facebook Login for Business uses one.
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_login_config_id: str = ""
    # A job that was running when the app stopped is queued again and
    # resumes, unless it was already started this many times: it fails.
    job_max_attempts: PositiveInt = 3
    # The posting worker (SPEC-v2 3.10) looks for due queued posts every
    # post_poll_s seconds. A passing upload failure is retried after
    # post_retry_base_s, doubled each attempt up to post_retry_max_s; the
    # post fails at its post_max_attempts-th failed upload. Rate limits: an
    # account starts at most one upload per post_account_gap_s seconds and
    # its platform's posts per day (post_schedule.DAILY_POSTS) per 24 h; a
    # platform listed in post_platform_hourly starts at most that many
    # uploads per hour over all its accounts.
    post_poll_s: PositiveFloat = 30.0
    post_max_attempts: PositiveInt = 5
    post_retry_base_s: PositiveFloat = 60.0
    post_retry_max_s: PositiveFloat = 3600.0
    post_account_gap_s: NonNegativeFloat = 60.0
    post_platform_hourly: dict[str, PositiveInt] = {}
    # A queued post whose time passed more than post_missed_grace_s before
    # the app started, and that was never tried, was missed while the app
    # was off: post_missed_policy posts it late or skips it.
    post_missed_policy: PostMissedPolicy = "post_late"
    post_missed_grace_s: NonNegativeFloat = 600.0
    # Public REST API /api/v1 (SPEC-v2 3.14): requests per minute per API
    # key; one more is answered 429 with Retry-After.
    api_rate_limit_per_min: PositiveInt = 120
    # Monthly caps of the usage meter (SPEC-v2 2.4); 0 means no cap. Once a
    # month's total reaches a cap, new jobs are refused until the next month.
    usage_cap_compute_hours: NonNegativeFloat = 0
    usage_cap_llm_tokens: NonNegativeFloat = 0
    usage_cap_api_calls: NonNegativeFloat = 0
    # Notifications (SPEC-v2 3.17) always show in the app. Email is sent only
    # if smtp_host is set (smtp_port 465 is implicit TLS, any other port
    # uses STARTTLS when the server offers it) to notify_email_to (empty:
    # smtp_from, else smtp_user); desktop_notifications also show them as
    # operating-system notifications. A usage cap that is quota_warn_percent
    # % used raises a quota warning once a month. The daily digest (drafts
    # waiting, posts today, submissions to do, estimated earnings) is made
    # once a day, from digest_time ("HH:MM", local time; empty: no digest).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    notify_email_to: str = ""
    desktop_notifications: bool = False
    quota_warn_percent: float = Field(default=80.0, gt=0, lt=100)
    digest_time: str = Field(default="08:00", pattern=r"^(([01]\d|2[0-3]):[0-5]\d)?$")
    # A clip keeps its latest clip_versions_kept versions (SPEC-v2 3.5
    # undo/redo history); older ones are dropped as new edits come in.
    clip_versions_kept: int = Field(default=100, ge=2)
    # Pro Edit (SPEC-v3): whether the app offers it (proedit/config.py).
    proedit: ProEditConfig = ProEditConfig()

    @model_validator(mode="before")
    @classmethod
    def _default_video_encoder(cls, data: Any) -> Any:
        """Fill an unset (empty) video_encoder with the default encoder of the
        ffmpeg in use (encoders.default_encoder)."""
        if isinstance(data, dict) and not data.get("video_encoder"):
            ffmpeg = str(data.get("ffmpeg_bin") or "").strip() or default_tool("ffmpeg")
            data = {**data, "video_encoder": encoders.default_encoder(ffmpeg)}
        return data

    def render_settings(self) -> RenderSettings:
        """Return the render settings with the video_encoder in use."""
        return self.render.model_copy(update={"encoder": self.video_encoder})

    @model_validator(mode="after")
    def _resolve_tools(self) -> "Settings":
        """Fill an unset (empty) ffmpeg_bin or ffprobe_bin with default_tool."""
        self.ffmpeg_bin = self.ffmpeg_bin.strip() or default_tool("ffmpeg")
        self.ffprobe_bin = self.ffprobe_bin.strip() or default_tool("ffprobe")
        return self

    @field_validator("always_hashtags", mode="before")
    @classmethod
    def _tidy_always_hashtags(cls, value: Any) -> Any:
        """Read a JSON list or comma-separated text; drop "#", blanks and
        repeats (any letter case)."""
        if isinstance(value, str):
            return tags_from_text(value)
        if isinstance(value, list):
            return clean_tags(str(item) for item in value)
        return value

    @field_validator("smtp_port", mode="before")
    @classmethod
    def _default_smtp_port(cls, value: Any) -> Any:
        """Read an empty SMTP_PORT (as .env.example has it) as the default."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return 587
        return value

    @field_validator("credit_template")
    @classmethod
    def _check_credit_template(cls, template: str) -> str:
        """Require a template that only uses CREDIT_FIELDS (credit_fields)."""
        credit_fields(template)
        return template

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_settings = YamlConfigSettingsSource(
            settings_cls,
            yaml_file="config.yaml",
            yaml_file_encoding="utf-8",
        )
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
            yaml_settings,
        )


settings = Settings()
