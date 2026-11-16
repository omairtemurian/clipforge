"""Pydantic schemas shared by the pipeline, database layer, and API.

Field names, literals, and constraints follow SPEC 5. This module is the single
source of truth for the frontend types (SPEC 0.9).
"""

import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any, Literal, Self, get_args
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)

from clipforge import config
from clipforge.aspect import PATTERN as ASPECT_PATTERN
from clipforge.aspect import check_aspect
from clipforge.languages import WHISPER_LANGUAGES
from clipforge.required_tags import clean_tags

# The kinds of video that curate has a prompt for; "auto" picks one of them.
ContentGenre = Literal[
    "comedy",
    "sports_commentary",
    "faith",
    "news",
    "vlog",
    "gaming",
    "podcast",
    "talk",
    "interview",
    "other",
]
Genre = Literal["auto", ContentGenre]
LengthPreset = Literal[
    "auto",
    "lt30",
    "0_60",
    "30_60",
    "60_90",
    "60_180",
    "90_180",
    "180_300",
    "300_600",
    "600_900",
    "custom",
]
# The longest clip, in seconds, that a custom length range may allow.
CUSTOM_LENGTH_MAX_S = 900.0
# Whether curate picks the clips (ai), the whole timeframe is one clip with
# captions and reframing only (captions_only), or the clips are the moments
# where search_terms are said, found without the LLM (keyword_search).
ClippingMode = Literal["ai", "captions_only", "keyword_search"]
# The most search terms, and the longest one, of a keyword search.
MAX_SEARCH_TERMS = 20
SearchTerm = Annotated[str, Field(max_length=100)]
# The token of an uploaded SRT file: {data_dir}/subtitles/<token>.srt.
SubtitlesId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
# 9:16, 1:1, 4:5, 16:9 or a custom "W:H" up to 4:1 (clipforge.aspect).
Aspect = Annotated[str, Field(pattern=ASPECT_PATTERN), AfterValidator(check_aspect)]
AudioEventKind = Literal["laugh", "applause", "cheer", "music"]
SignalKind = Literal[
    "laugh", "applause", "cheer", "music", "scene_cut", "silence", "energy_peak"
]
# fill, fit and split (SPEC 6.8); grid: three speakers; pip: picture in
# picture; screenshare and gameplay: the video with a facecam; square_blur: a
# square of the subject over a blurred copy (pipeline/layouts).
Layout = Literal[
    "fill", "fit", "split", "grid", "pip", "screenshare", "gameplay", "square_blur"
]
# The layout new clips get (SPEC-v2 3.3): auto, the one reframe picks per
# clip; dynamic, one per segment by its speakers and scene
# (pipeline/layout_switch); or this layout for every clip.
DefaultLayout = Literal["auto", "dynamic", Layout]
# How often new clips zoom out from fill to square_blur or fit for a moment
# (pipeline/layout_auto); off: never.
ZoomOutIntensity = Literal["off", "subtle", "balanced", "frequent"]
# The kinds of video that reframe has a preset for (pipeline/reframe_presets).
ReframePreset = Literal["podcast-2", "standup", "gaming", "vlog"]
# How reframe's crop windows move (pipeline/camera_motion): calm and normal
# rest and re-aim in eased moves, fast pans at a capped speed (the motion
# before this setting).
CameraMotion = Literal["calm", "normal", "fast"]
# How a scene of a clip places its fill window: as reframe planned it (auto),
# following a subject the editor picked (track), or at keyframes (fixed).
SceneMode = Literal["auto", "track", "fixed"]
ClipStatus = Literal["candidate", "rendering", "rendered", "failed"]
# Whether a clip is the one that the pipeline made (original) or a Pro Edit
# variant of another clip (SPEC-v3 0.13, 6).
ClipVariant = Literal["original", "pro_edit"]
# The Pro Edit presets (SPEC-v3 3.4) and how heavy an edit may be (3.1).
ProEditPreset = Literal[
    "clean_pro", "dark_edit", "phonk_edit", "cinematic", "skull_moment", "glitch"
]
ProEditIntensity = Literal["clean", "standard", "pro", "extreme"]
# What a Pro Edit does to the background behind the cut-out subject
# (SPEC-v3 3.3 motion): nothing, a blur or a swap to a solid color.
ProEditBackground = Literal["keep", "blur", "swap"]
# Whether a campaign allows heavily edited clips: the string "true" or
# "false" once the owner has read its rules, else "unknown" (SPEC-v3 6).
HeavyEditsAllowed = Literal["true", "false", "unknown"]
JobKind = Literal["process", "render", "reprompt", "proedit"]
JobStatus = Literal["queued", "running", "done", "failed"]
LogoPosition = Literal["tl", "tr", "bl", "br"]
CaptionPosition = Literal["top", "middle", "lower_third", "bottom"]
# How caption words move (pipeline/caption_effects): not at all, the spoken
# word growing in (pop) or springing in (bounce), each page of lines fading
# in (fade), words showing only once spoken (reveal), an emphasis word
# shaking (shake), the spoken word underlined (underline) or on a pill of
# its color (pill), or the other words drawn as outlines only (hollow).
CaptionAnimation = Literal[
    "none",
    "pop",
    "bounce",
    "fade",
    "reveal",
    "shake",
    "underline",
    "pill",
    "hollow",
]
# The words of a caption line and the lines shown at once (a page).
CAPTION_WORDS_MIN, CAPTION_WORDS_MAX = 1, 6
CAPTION_LINES_MIN, CAPTION_LINES_MAX = 1, 2
# What a cut that speech cleanup suggests removes: filler words, a pause, or
# a bad take (a repeated or abandoned sentence, found by the LLM).
CleanupKind = Literal["filler", "pause", "bad_take"]
# Speech cleanup's pause threshold: a gap longer than this is a pause (s).
CLEANUP_PAUSE_S, CLEANUP_PAUSE_MIN_S, CLEANUP_PAUSE_MAX_S = 0.6, 0.3, 10.0
# The custom filler words of one cleanup, and the bad takes of one reply.
CLEANUP_EXTRA_FILLERS_MAX, BAD_TAKES_MAX = 50, 20
# The suggestions that one apply of speech cleanup takes.
CLEANUP_ITEMS_MAX = 2000
# What the fit layout shows around the video: a blurred copy of it, or black.
FitBackground = Literal["blur", "black"]
# What a timeline item plays: "source" is a section of the source video;
# "video", "image" and "audio" play a library asset; "text" draws its text.
TrackItemKind = Literal["source", "video", "image", "text", "audio"]
# The tracks of a clip's timeline (SPEC-v2 3.5, 4).
TrackName = Literal["video", "broll", "overlays", "text", "music", "sfx", "voiceover"]
# How a text overlay comes in or goes out: every one but "none" fades;
# slides move it a part of the frame, "pop" grows/shrinks its font.
TextAnimation = Literal[
    "none", "fade", "slide_up", "slide_down", "slide_left", "slide_right", "pop"
]
# A transition at a cut of a clip's render (SPEC-v2 3.5; ffmpeg xfade
# fade, zoomin, hblur and slideleft: pipeline/transitions).
TransitionKind = Literal["crossfade", "zoom_punch", "whip", "slide"]
# Where the text of a clip's viral hook comes from (POST /clips/{id}/hook):
# the opening words of its captions, a line the LLM writes about its theme,
# or the text given.
HookSource = Literal["captions", "theme", "text"]
# The longest text of a viral hook (as long as a v1 hook_text).
HOOK_TEXT_MAX = 60
# How long a viral hook shows, in seconds: the first 2-3 s of the clip.
HOOK_SECONDS_MIN, HOOK_SECONDS_MAX, HOOK_SECONDS = 2.0, 3.0, 2.5
# What a motion graphic marks (pipeline/motion_graphics): a person's or a
# company's name or a key phrase (a lower-third), a number or a date (a
# number callout).
MotionGraphicKind = Literal["name", "number", "date", "phrase"]
# The longest text and label of a motion graphic, and the longest quote.
MOTION_GRAPHIC_TEXT_MAX, MOTION_GRAPHIC_QUOTE_MAX = 40, 120
# The most motion graphics the LLM may pick for a clip in one reply.
MOTION_GRAPHIC_PICKS_MAX = 10
# What a library asset is (SPEC-v2 4).
AssetKind = Literal["video", "image", "audio", "font", "logo", "music", "sfx"]
# Why the owner may use a project's source video (SPEC-v2 1.6).
SourceRights = Literal["own", "permission", "cc_by", "public_domain", "other"]
# Where a clipping campaign is run, how a clipper joins it and its state
# (SPEC-v2 3.18).
CampaignBoard = Literal["whop", "direct", "other"]
CampaignBadge = Literal["open", "register_first", "apply_first", "paid"]
CampaignStatus = Literal["active", "paused", "ended"]
# The platforms that a campaign can allow: those of the publishers (T46-T47).
CampaignPlatform = Literal["youtube", "tiktok", "instagram"]
# The social platforms of the publishers and the states of a post (SPEC-v2
# 3.10, 4).
SocialPlatform = Literal["youtube", "tiktok", "instagram", "facebook", "x", "linkedin"]
PostStatus = Literal[
    "draft", "queued", "uploading", "published", "failed", "canceled", "skipped"
]
CREDIT_LINE_MAX = 200
CAMPAIGN_TEXT_MAX = 2000
PROJECT_TITLE_MAX = 200
# The longest reprompt request.
PROMPT_MAX = 2000
CHAPTER_TITLE_MAX = 100
CHAPTER_SUMMARY_MAX = 400

Score = Annotated[int, Field(ge=0, le=99)]
UnitInterval = Annotated[float, Field(ge=0, le=1)]
Hashtag = Annotated[str, Field(pattern=r"^[^#]+$")]
HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
CutRange = tuple[float, float]
# One non-ASCII character, optionally followed by VARIATION SELECTOR-16.
Emoji = Annotated[str, Field(pattern=r"^[^\x00-\x7f]\ufe0f?$")]


def _http_url(url: str) -> str:
    """Require an http(s) URL with a host; return it stripped."""
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("url must be an http(s) URL")
    return url.strip()


# A video link; local files go through POST /projects/upload.
HttpUrl = Annotated[str, AfterValidator(_http_url)]


def _source_span(span: tuple[float, float]) -> tuple[float, float]:
    """Require 0 <= start < end of a [start, end] section of the source."""
    if not 0 <= span[0] < span[1]:
        raise ValueError("a segment needs 0 <= start < end")
    return span


# A [start, end] section of the source video, in seconds (SPEC-v2 4).
SourceSpan = Annotated[tuple[float, float], AfterValidator(_source_span)]


def _whisper_language(code: str) -> str:
    """Accept a language code that Whisper knows (clipforge.languages)."""
    if code not in WHISPER_LANGUAGES:
        raise ValueError(f"{code!r} is not a Whisper language code")
    return code


SpeechLanguage = Annotated[str, AfterValidator(_whisper_language)]


class Word(BaseModel):
    """A transcribed word with its timing in seconds."""

    text: str
    start: float
    end: float
    speaker: str
    prob: float
    # True when the time is spread over a subtitle cue (an uploaded SRT or
    # VTT), not heard by Whisper.
    approximate: bool = False


class CaptionMark(BaseModel):
    """What the AI or the editor says of one caption word, the one that
    starts at start (source seconds, to the millisecond): emphasis forces the
    word to be an emphasis word or not (None: the clip's emphasis_words
    decide), emoji is shown after it ("": none, None: the template's emoji
    map decides) and color is the word's color while it is not the spoken
    word, over the emphasis and speaker colors (None: they decide). A "user"
    mark beats an "ai" mark of the same word."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    emphasis: bool | None = None
    emoji: Emoji | Literal[""] | None = None
    # True: censor the word, False: never censor it, None: the clip's
    # CaptionCensor and the censor lists decide (pipeline/censor).
    censor: bool | None = None
    color: HexColor | None = None
    source: Literal["ai", "user"] = "user"


class CaptionCue(BaseModel):
    """One cue of translated captions: text shown from start to end (source
    seconds), the time of the words it translates, said by speaker (the
    transcript's label, "" if unknown)."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(min_length=1, max_length=500, pattern=r"\S")
    speaker: str = ""


class CaptionTranslation(BaseModel):
    """A clip's captions in another language (pipeline/caption_translate):
    the language's Whisper code and the translated cues, in time order."""

    model_config = ConfigDict(extra="forbid")

    language: SpeechLanguage
    cues: list[CaptionCue]


class CaptionTranslationRequest(BaseModel):
    """POST /clips/{id}/caption-translation: the language (a Whisper code)
    to translate the clip's captions into."""

    language: SpeechLanguage


class TranslatedCue(BaseModel):
    """One cue as the LLM translates it: its number in the numbered cues
    that the prompt lists (from 0) and its text in the target language."""

    index: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=500, pattern=r"\S")


class TranslatedCues(BaseModel):
    """The reply to the caption translation prompt, {"cues": [...]}."""

    cues: list[TranslatedCue]


CensorMode = Literal["beep", "mute"]


class CaptionCensor(BaseModel):
    """How a clip censors swear words (SPEC-v2 3.4, pipeline/censor): with
    auto, the words of the default and custom censor lists; always, the
    words a CaptionMark censors. A censored word's caption is masked
    ("f***") and its sound beeped or muted, as mode says."""

    model_config = ConfigDict(extra="forbid")

    auto: bool = True
    mode: CensorMode = "beep"


class CaptionStyle(BaseModel):
    """What the editor changes of a clip's caption template: each field that
    is set replaces the template's (size in pixels of the output frame); an
    unset field keeps the template's. font must name a bundled font
    (captions_templates.style_problems checks it when a clip is saved).

    speaker_colors (diarized speaker -> color of that speaker's words),
    word_marks (per-word emphasis, emoji and censor), translation (the
    captions in another language, shown instead of the transcript's words)
    and censor (None: only the words that marks censor, beeped) belong to
    the clip, not to a template: CaptionTemplate has no such fields."""

    model_config = ConfigDict(extra="forbid")

    size: int | None = Field(default=None, ge=20, le=200)
    primary_color: HexColor | None = None
    highlight_color: HexColor | None = None
    emphasis_color: HexColor | None = None
    position: CaptionPosition | None = None
    uppercase: bool | None = None
    emoji: bool | None = None
    font: str | None = Field(default=None, min_length=1, max_length=100)
    outline: float | None = Field(default=None, ge=0, le=20)
    outline_color: HexColor | None = None
    shadow: float | None = Field(default=None, ge=0, le=20)
    box: bool | None = None
    max_lines: int | None = Field(
        default=None, ge=CAPTION_LINES_MIN, le=CAPTION_LINES_MAX
    )
    max_words_per_line: int | None = Field(
        default=None, ge=CAPTION_WORDS_MIN, le=CAPTION_WORDS_MAX
    )
    animation: CaptionAnimation | None = None
    speaker_colors: dict[str, HexColor] | None = None
    word_marks: list[CaptionMark] | None = None
    translation: CaptionTranslation | None = None
    censor: CaptionCensor | None = None


class Segment(BaseModel):
    """A transcript segment made of timed words."""

    id: int
    start: float
    end: float
    text: str
    words: list[Word]
    speaker: str


class Transcript(BaseModel):
    """The full transcript of a source video."""

    language: str
    duration: float
    segments: list[Segment]
    # True when the words' times are spread over subtitle cues (an uploaded
    # SRT or VTT), not heard by Whisper.
    approximate_times: bool = False


class SignalEvent(BaseModel):
    """An audio or video event detected in the source."""

    kind: SignalKind
    start: float
    end: float
    intensity: UnitInterval


class SignalList(RootModel[list[SignalEvent]]):
    """Signal events as a JSON array: the content of signals.json (SPEC 6.3)."""


class AudioEventTrack(BaseModel):
    """What YAMNet heard of one kind of non-speech audio event, per second.

    scores[i] (0..1) is the highest score of the kind in the second that
    starts at start + i, in source seconds.
    """

    kind: AudioEventKind
    start: float
    scores: list[UnitInterval]


class AudioEventList(RootModel[list[AudioEventTrack]]):
    """One track per audio event kind: the content of audio_events.json."""


# Why a frame was captioned: it is the first of a scene, or a regular sample.
FrameSampleReason = Literal["scene_cut", "interval"]


class FrameCaption(BaseModel):
    """What the vision model saw in the source frame at time (source
    seconds), which was sampled for reason."""

    time: float
    reason: FrameSampleReason
    caption: str


class FrameCaptionList(BaseModel):
    """The content of frame_captions.json: the Ollama vision model that
    wrote the captions, and the captions by time."""

    model: str
    captions: list[FrameCaption]


class MotionTrack(BaseModel):
    """How much the picture moves, per second: the content of motion.json.

    scores[i] is the motion energy of the second that starts at start + i
    (source seconds): the median, over the frame pairs of that second, of
    the mean absolute difference of two consecutive small grey frames, as a
    fraction of full scale (0: a still picture).
    """

    start: float
    scores: list[UnitInterval]


class CaptionColors(BaseModel):
    """The caption colors that a processing preset gives the clips of a
    project over any caption template (None keeps the template's): the
    words (primary_color), the spoken word (highlight_color) and the
    emphasis words (emphasis_color)."""

    model_config = ConfigDict(extra="forbid")

    primary_color: HexColor | None = None
    highlight_color: HexColor | None = None
    emphasis_color: HexColor | None = None


class ProcessingSettings(BaseModel):
    """Options chosen for processing one project."""

    genre: Genre = "auto"
    # The clip lengths curate may pick; a clip fits if it fits any of them.
    length_presets: list[LengthPreset] = Field(
        default_factory=lambda: list[LengthPreset](["auto"]), min_length=1
    )
    # The seconds range of the "custom" length preset.
    custom_length_min_s: float | None = Field(default=None, ge=0)
    custom_length_max_s: float | None = Field(default=None, gt=0)
    timeframe_start: float | None = Field(default=None, ge=0)
    timeframe_end: float | None = Field(default=None, ge=0)
    num_clips: int = Field(
        default_factory=lambda: config.settings.default_num_clips,
        ge=1,
        le=30,
        validate_default=True,
    )
    aspect: Aspect = "9:16"
    caption_template: str = "karaoke_bold"
    # Colors for the captions of every new clip, whatever the template.
    caption_colors: CaptionColors = Field(default_factory=CaptionColors)
    keyword_prompt: str | None = None
    remove_fillers: bool = False
    # Jump cuts of the silences longer than auto_cut_min_pause_s (auto_cut).
    auto_cut: bool = True
    auto_cut_min_pause_s: float = Field(default=0.5, ge=0.2, le=3)
    # Punch-ins on emphasis, new sentences and reactions (pipeline/auto_zoom).
    auto_zoom: bool = True
    # The LLM's one-line opening text over the first seconds of each clip.
    auto_headline: bool = True
    # Brightness, contrast and colour levelled in the render (render_graph).
    auto_color: bool = False
    # False: clips get no word captions (an auto headline still shows).
    captions: bool = True
    # The Whisper language code of the speech; None: Whisper detects it.
    language: SpeechLanguage | None = None
    # An uploaded SRT or VTT used as the transcript instead of Whisper.
    subtitles_id: SubtitlesId | None = None
    clipping: ClippingMode = "ai"
    # AI clipping also reads what is seen and heard (motion, frame captions,
    # audio events and scene cuts), so moments without speech can be clips.
    clip_anything: bool = False
    # The words or phrases a keyword_search finds in the transcript.
    search_terms: list[SearchTerm] = Field(
        default_factory=list, max_length=MAX_SEARCH_TERMS
    )
    brand_template_id: int | None = None
    # How reframe frames the clips of a kind of video; None: the defaults.
    reframe_preset: ReframePreset | None = None
    default_layout: DefaultLayout = "auto"
    # Zoom-out moments of auto and dynamic layouts (pipeline/layout_auto).
    zoom_out_moments: ZoomOutIntensity = "balanced"
    # How the crop windows move; picking a reframe preset in the UI sets
    # the preset's (pipeline/reframe_presets).
    camera_motion: CameraMotion = "calm"

    @model_validator(mode="before")
    @classmethod
    def _upgrade_length_preset(cls, data: Any) -> Any:
        """Read v1 settings, which had one length_preset, as length_presets,
        and the clipping "none" of settings saved before captions_only."""
        if isinstance(data, dict) and "length_preset" in data:
            data = dict(data)
            legacy = data.pop("length_preset")
            data.setdefault("length_presets", [legacy])
        if isinstance(data, dict) and data.get("clipping") == "none":
            data = {**data, "clipping": "captions_only"}
        return data

    @field_validator("length_presets")
    @classmethod
    def _tidy_length_presets(cls, presets: list[LengthPreset]) -> list[LengthPreset]:
        """Keep each preset once, in the order of LengthPreset; "auto" goes
        when other presets are chosen."""
        chosen = [p for p in get_args(LengthPreset) if p in presets]
        return [p for p in chosen if p != "auto"] or ["auto"]

    @field_validator("search_terms")
    @classmethod
    def _tidy_search_terms(cls, terms: list[str]) -> list[str]:
        """Collapse the whitespace of each term and drop blank terms and
        repeats, which differ only in case or spacing."""
        tidy: dict[str, str] = {}
        for term in terms:
            words = " ".join(term.split())
            if words:
                tidy.setdefault(words.casefold(), words)
        return list(tidy.values())

    @model_validator(mode="after")
    def _check_search_terms(self) -> Self:
        """Require a search term for a keyword_search."""
        if self.clipping == "keyword_search" and not self.search_terms:
            raise ValueError("a keyword search needs at least one search term")
        return self

    @model_validator(mode="after")
    def _check_custom_length(self) -> Self:
        """Require min < max <= CUSTOM_LENGTH_MAX_S for a custom length range,
        which both bounds must give when "custom" is chosen."""
        low, high = self.custom_length_min_s, self.custom_length_max_s
        if "custom" in self.length_presets and (low is None or high is None):
            raise ValueError("a custom length needs custom_length_min_s and _max_s")
        if high is not None and high > CUSTOM_LENGTH_MAX_S:
            raise ValueError(
                f"custom_length_max_s must be at most {CUSTOM_LENGTH_MAX_S:g}"
            )
        if low is not None and high is not None and low >= high:
            raise ValueError(
                "custom_length_min_s must be less than custom_length_max_s"
            )
        return self

    @property
    def custom_length(self) -> tuple[float, float] | None:
        """The (min, max) seconds of the custom length, if one is set."""
        low, high = self.custom_length_min_s, self.custom_length_max_s
        return None if low is None or high is None else (low, high)

    @model_validator(mode="after")
    def _check_timeframe(self) -> Self:
        """Reject a timeframe whose end is not after its start."""
        start = self.timeframe_start or 0.0
        if self.timeframe_end is not None and self.timeframe_end <= start:
            raise ValueError("timeframe_end must be greater than timeframe_start")
        return self


PresetName = Annotated[str, Field(min_length=1, max_length=60, pattern=r"\S")]


class ProcessingPreset(BaseModel):
    """A named set of processing settings that the user saved ("My
    presets"); like the saved default, it holds no timeframe or subtitles,
    which belong to one video."""

    name: PresetName
    settings: ProcessingSettings


class SourceMeta(BaseModel):
    """What ingest learned about a source video; stored as meta.json (SPEC 6.1).

    Later steps only consider the [timeframe_start, timeframe_end] seconds of
    the source. channel and channel_url name the uploader of a downloaded
    video (for the credit line); they are None for local files.
    """

    title: str
    duration: float = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    timeframe_start: float = Field(ge=0)
    timeframe_end: float
    channel: str | None = None
    channel_url: str | None = None

    @model_validator(mode="after")
    def _check_timeframe(self) -> Self:
        """Require timeframe_start < timeframe_end <= duration."""
        if not self.timeframe_start < self.timeframe_end <= self.duration:
            raise ValueError("timeframe must satisfy start < end <= duration")
        return self


class ClipCandidate(BaseModel):
    """A clip proposed by the LLM; times are seconds from the video start."""

    start: float
    end: float
    title: str = Field(max_length=70)
    hook_text: str = Field(max_length=60)
    description: str = Field(max_length=300)
    hashtags: list[Hashtag] = Field(min_length=3, max_length=8)
    emphasis_words: list[str]
    reason: str
    hook: Score
    flow: Score
    value: Score
    trend: Score


class CandidateList(BaseModel):
    """Clip candidates as {"clips": [...]}: the reply the curate prompt asks
    the LLM for (SPEC 6.5), and the content of candidates.json."""

    clips: list[ClipCandidate]


class Scores(BaseModel):
    """Virality score breakdown of a clip."""

    overall: Score
    hook: Score
    flow: Score
    value: Score
    trend: Score
    laugh: UnitInterval
    energy: UnitInterval


class ScoredCandidate(ClipCandidate):
    """A clip candidate with its virality scores (SPEC 6.6)."""

    scores: Scores


class ScoredList(BaseModel):
    """Scored clip candidates as {"clips": [...]}, best overall score first:
    the content of scored.json (SPEC 6.6) and snapped.json (SPEC 6.7)."""

    clips: list[ScoredCandidate]


class CropPoint(BaseModel):
    """Where the editor's crop tool put a clip's fill window at t seconds
    into the source: the window's center, in fractions of the source
    frame's width (x) and height (y)."""

    t: float = Field(ge=0)
    x: UnitInterval
    y: UnitInterval


class FrameBox(BaseModel):
    """A box on the source frame: its top-left corner and size, in
    fractions of the frame's width (x, width) and height (y, height)."""

    x: UnitInterval
    y: UnitInterval
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def _check_inside(self) -> Self:
        """Reject a box that reaches past the frame's right or bottom edge."""
        if self.x + self.width > 1 + 1e-6 or self.y + self.height > 1 + 1e-6:
            raise ValueError("a box must be inside the frame")
        return self


class Framing(BaseModel):
    """How the editor frames a clip on top of its crop plan
    (pipeline/framing).

    aspect is the clip's (None: the project's); background is what the fit
    layout shows around the video. The crop tool sizes the fill window to
    scale times the planned window (1: the whole frame height) and puts it
    at points, by time: with tracker on, the window follows the subject,
    moved so it is at each point at that point's time; with tracker off, it
    stays where the points put it (between two points it moves from one to
    the other). facecam is the box the user drew around the facecam for the
    screenshare and gameplay layouts (None: the one reframe found).
    """

    aspect: Aspect | None = None
    background: FitBackground = "blur"
    scale: float = Field(default=1, ge=0.25, le=1)
    points: list[CropPoint] = Field(default_factory=list)
    tracker: bool = True
    facecam: FrameBox | None = None


class TrackSeed(BaseModel):
    """The box the editor drew (or clicked) around a subject to track, at t
    seconds into the source: its top-left corner and size, in fractions of
    the source frame's width (x, width) and height (y, height)."""

    t: float = Field(ge=0)
    x: UnitInterval
    y: UnitInterval
    width: UnitInterval
    height: UnitInterval


class SceneReframe(BaseModel):
    """How a clip frames one scene, start to end seconds of the source
    (pipeline/scenes). layout is the scene's; with fill, mode says where
    its fill window is: auto follows the clip's crop plan (with the clip's
    crop offset and crop tool), track and fixed put the window's center at
    crop_keyframes (linear between them, held before the first and after
    the last; fixed without keyframes holds the auto window of the scene's
    start). The window is scale times the planned window. track_seed is the
    box that the track mode's keyframes were tracked from."""

    start: float = Field(ge=0)
    end: float
    mode: SceneMode = "auto"
    layout: Layout = "fill"
    crop_keyframes: list[CropPoint] = Field(default_factory=list)
    scale: float = Field(default=1, ge=0.25, le=1)
    track_seed: TrackSeed | None = None

    @model_validator(mode="after")
    def _check_times(self) -> Self:
        """Reject a scene whose end is not after its start."""
        if self.end <= self.start:
            raise ValueError("a scene's end must be after its start")
        return self


class ClipScenes(BaseModel):
    """A clip's scenes (GET /clips/{id}/scenes): the scene cuts of its
    source, in seconds, and its scenes as stored, or split at the cuts
    inside it if it has none stored (default_scenes)."""

    cuts: list[float]
    scenes: list[SceneReframe]


class SceneTrackRequest(BaseModel):
    """A scene to track (POST /clips/{id}/scenes/track): start to end
    seconds of the source, and the box (or click: no size) around the
    subject to follow."""

    start: float = Field(ge=0)
    end: float
    seed: TrackSeed

    @model_validator(mode="after")
    def _check_span(self) -> Self:
        """Reject a span that is empty or does not hold the seed's time."""
        if self.end <= self.start:
            raise ValueError("a scene's end must be after its start")
        if not self.start <= self.seed.t <= self.end:
            raise ValueError("the seed must be inside the scene")
        return self


class SceneTrack(BaseModel):
    """The crop keyframes that follow a tracked subject through a scene
    (pipeline/click_track), and the seed with the box that was tracked."""

    keyframes: list[CropPoint]
    seed: TrackSeed


class CropKeyframeSet(BaseModel):
    """The body of PUT /clips/{id}/crop-keyframes (pipeline/keyframes): the
    crop box dragged to center (x, y), in fractions of the source frame, at
    t seconds of the source, and resized to scale times the planned window
    (None: the scene's scale is kept)."""

    model_config = ConfigDict(extra="forbid")

    t: float = Field(ge=0)
    x: UnitInterval
    y: UnitInterval
    scale: float | None = Field(default=None, ge=0.25, le=1)


class TrackItem(BaseModel):
    """An item on a track of a clip's timeline (SPEC-v2 4).

    A "source" item plays the [start, end] seconds of the source video
    (one of the clip's segments) and has no asset_id. The items of the
    other tracks show from start to end seconds of the rendered clip (after
    its cuts); "video", "image" and "audio" items play asset asset_id, a
    "text" item has none. props holds the settings of the item's track
    (BrollProps, OverlayProps, TextProps, AudioProps or, on the music track,
    MusicProps and on the voiceover track VoiceoverProps; clipforge.timeline).
    """

    id: str = Field(min_length=1)
    kind: TrackItemKind
    asset_id: int | None = None
    start: float = Field(ge=0)
    end: float
    props: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_times(self) -> Self:
        """Reject an item whose end is not after its start."""
        if self.end <= self.start:
            raise ValueError("a track item's end must be after its start")
        return self


class Timeline(BaseModel):
    """The tracks of a clip, each a list of items (SPEC-v2 4); the video
    track holds a "source" item for each of the clip's segments."""

    video: list[TrackItem] = Field(default_factory=list)
    broll: list[TrackItem] = Field(default_factory=list)
    overlays: list[TrackItem] = Field(default_factory=list)
    text: list[TrackItem] = Field(default_factory=list)
    music: list[TrackItem] = Field(default_factory=list)
    sfx: list[TrackItem] = Field(default_factory=list)
    voiceover: list[TrackItem] = Field(default_factory=list)


class TimelinePatch(BaseModel):
    """The body of PATCH /clips/{id}/tracks: the tracks to replace (unset or
    null tracks are kept). The video track follows the clip's segments, so
    it is not here."""

    model_config = ConfigDict(extra="forbid")

    broll: list[TrackItem] | None = None
    overlays: list[TrackItem] | None = None
    text: list[TrackItem] | None = None
    music: list[TrackItem] | None = None
    sfx: list[TrackItem] | None = None
    voiceover: list[TrackItem] | None = None


BrollMode = Literal["cutaway", "pip"]


class BrollProps(BaseModel):
    """The props of a B-roll item: a "cutaway" asset fills the frame
    (scaled to cover it, centered); a "pip" (picture-in-picture) asset is
    width times the frame's width wide, centered at (x, y) in fractions of
    the frame. A video asset plays from offset seconds, muted."""

    model_config = ConfigDict(extra="forbid")

    offset: float = Field(default=0, ge=0)
    mode: BrollMode = "cutaway"
    x: UnitInterval = 0.5
    y: UnitInterval = 0.3
    width: float = Field(default=0.8, gt=0, le=1)


class OverlayProps(BaseModel):
    """The props of an overlay item: the asset, width times the frame's
    width wide, centered at (x, y) in fractions of the frame, at opacity; a
    video asset plays from offset seconds, muted."""

    model_config = ConfigDict(extra="forbid")

    x: UnitInterval = 0.5
    y: UnitInterval = 0.5
    width: float = Field(default=0.3, gt=0, le=1)
    opacity: UnitInterval = 1.0
    offset: float = Field(default=0, ge=0)


class TextProps(BaseModel):
    """The props of a text item (a text overlay): text in font (a bundled or
    uploaded font), size times the frame's height tall, in color, outlined
    in stroke (stroke_width times the font size wide) if stroke is set, on
    a box of color box at box_opacity if box is set, centered at (x, y) in
    fractions of the frame. It comes in with animation_in over in_seconds
    from the item's start and goes out with animation_out over out_seconds
    up to its end (pipeline/text_overlay)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200)
    font: str = Field(default="Montserrat ExtraBold", min_length=1, max_length=100)
    size: float = Field(default=0.06, gt=0, le=0.5)
    color: HexColor = "#FFFFFF"
    stroke: HexColor | None = None
    stroke_width: float = Field(default=0.08, gt=0, le=0.3)
    box: HexColor | None = None
    box_opacity: UnitInterval = 1.0
    x: UnitInterval = 0.5
    y: UnitInterval = 0.2
    animation_in: TextAnimation = "none"
    animation_out: TextAnimation = "none"
    in_seconds: float = Field(default=0.4, gt=0, le=3)
    out_seconds: float = Field(default=0.4, gt=0, le=3)


class AudioProps(BaseModel):
    """The props of a music, sound effect or voiceover item: the asset from
    offset seconds, at volume (1: as recorded), mixed with the clip's
    sound."""

    model_config = ConfigDict(extra="forbid")

    volume: float = Field(default=1.0, ge=0, le=2)
    offset: float = Field(default=0, ge=0)


MUSIC_FADE_MAX = 10.0


class MusicProps(AudioProps):
    """The props of a music item (SPEC-v2 3.5, pipeline/music): an
    AudioProps whose file loops for as long as the item lasts, fading in
    over fade_in seconds from its start and out over fade_out seconds to
    its end, and, if duck, dipping under the clip's speech (a sidechain
    compressor keyed by the clip's sound)."""

    fade_in: float = Field(default=0.0, ge=0, le=MUSIC_FADE_MAX)
    fade_out: float = Field(default=0.0, ge=0, le=MUSIC_FADE_MAX)
    duck: bool = True


# The TTS engines of AI voiceover (engines/tts), the longest text of one
# voiceover item and the speeds a voice may speak at (Kokoro's limits).
TtsEngineName = Literal["kokoro", "piper"]
VOICEOVER_TEXT_MAX = 1000
VOICE_ID_MAX = 200
VOICEOVER_SPEED_MIN, VOICEOVER_SPEED_MAX = 0.5, 2.0
VoiceoverText = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=VOICEOVER_TEXT_MAX
    ),
]
VoiceId = Annotated[str, StringConstraints(min_length=1, max_length=VOICE_ID_MAX)]
VoiceoverSpeed = Annotated[float, Field(ge=VOICEOVER_SPEED_MIN, le=VOICEOVER_SPEED_MAX)]


class VoiceoverProps(AudioProps):
    """The props of a voiceover item (SPEC-v2 3.5, pipeline/voiceover): an
    AudioProps; text, voice (a TtsVoice id) and speed when a TTS voice
    spoke it (None for a recording from the media library), and, if duck,
    the clip's own sound is lowered while the item plays."""

    text: VoiceoverText | None = None
    voice: VoiceId | None = None
    speed: VoiceoverSpeed = 1.0
    duck: bool = True


class TtsVoice(BaseModel):
    """A voice of an installed TTS engine (GET /api/voices): id is
    "<engine>:<voice>" (a Piper voice with several speakers:
    "piper:<voice>:<speaker>"), name what the UI shows, language a
    BCP 47 tag, gender if the engine says, and the license of the voice
    model."""

    id: str
    engine: TtsEngineName
    name: str
    language: str
    gender: Literal["female", "male"] | None
    license: str


class VoiceoverCreate(BaseModel):
    """The body of POST /clips/{id}/voiceover: text that voice speaks at
    speed, put on the voiceover track from start seconds of the rendered
    clip at volume, ducking the clip's sound if duck."""

    model_config = ConfigDict(extra="forbid")

    text: VoiceoverText
    voice: VoiceId
    start: float = Field(ge=0)
    speed: VoiceoverSpeed = 1.0
    volume: float = Field(default=1.0, ge=0, le=2)
    duck: bool = True


class VoiceoverPatch(BaseModel):
    """The body of PATCH /clips/{id}/voiceover/{item_id}: what to change
    (unset fields are kept). New text, voice or speed speaks it again;
    start moves it."""

    model_config = ConfigDict(extra="forbid")

    text: VoiceoverText | None = None
    voice: VoiceId | None = None
    start: float | None = Field(default=None, ge=0)
    speed: VoiceoverSpeed | None = None
    volume: float | None = Field(default=None, ge=0, le=2)
    duck: bool | None = None


class Transition(BaseModel):
    """A transition at a cut of a clip's render: kind over duration seconds,
    centred on the cut (pipeline/transitions)."""

    model_config = ConfigDict(extra="forbid")

    kind: TransitionKind
    duration: float = Field(default=0.3, ge=0.1, le=1)


class ClipTransitions(BaseModel):
    """The transitions of a clip's render (SPEC-v2 3.5): auto at every jump
    cut (a cut inside a section: its cut ranges, the auto cut's too), and
    sections[i] at the cut from the i-th to the next section in play order
    (manual; None, or no entry: a hard cut). Entries past the clip's last
    section boundary are kept but not used."""

    model_config = ConfigDict(extra="forbid")

    auto: Transition | None = None
    sections: list[Transition | None] = Field(default_factory=list, max_length=100)


HookText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=HOOK_TEXT_MAX),
]
HookSeconds = Annotated[float, Field(ge=HOOK_SECONDS_MIN, le=HOOK_SECONDS_MAX)]


class ClipHook(BaseModel):
    """The viral hook of a clip (SPEC-v2 3.5, pipeline/hooks): over the
    first duration seconds of its render, the hook template template
    (clipforge.hooks_templates) draws text with its animations, punches
    in on the frames and plays its whoosh. While a clip has one, its v1
    hook_text is not drawn."""

    model_config = ConfigDict(extra="forbid")

    template: str = Field(min_length=1, max_length=40)
    text: HookText
    duration: HookSeconds = HOOK_SECONDS


class HookApply(BaseModel):
    """The body of POST /clips/{id}/hook: give the clip the hook template
    template for duration seconds, its text taken from source: the opening
    words of its captions, a line the LLM writes about its theme, or text
    (which source "text" needs). duration None: the template's."""

    model_config = ConfigDict(extra="forbid")

    template: str = Field(min_length=1, max_length=40)
    source: HookSource = "captions"
    text: HookText | None = None
    duration: HookSeconds | None = None

    @model_validator(mode="after")
    def _check_text(self) -> Self:
        """Reject source "text" without text, and text with another source."""
        if (self.source == "text") != (self.text is not None):
            raise ValueError('text is needed with source "text", and only then')
        return self


class HookEdit(BaseModel):
    """The body of PATCH /clips/{id}/hook: the fields of the clip's hook to
    change (unset or null: kept)."""

    model_config = ConfigDict(extra="forbid")

    template: str | None = Field(default=None, min_length=1, max_length=40)
    text: HookText | None = None
    duration: HookSeconds | None = None


class HookTemplateInfo(BaseModel):
    """A hook template as GET /hook-templates lists it: name (what
    ClipHook.template names), label and description to show, the seconds
    a hook lasts by default, the most its punch-in magnifies the frames
    (1: none) and whether it plays a whoosh."""

    name: str
    label: str
    description: str
    duration: float
    punch: float
    sound: bool


class HookLine(BaseModel):
    """The LLM's reply with one line of text for a clip: a hook line about
    its theme or its headline."""

    text: str = Field(min_length=1, max_length=HOOK_TEXT_MAX)


class HeadlineApply(BaseModel):
    """The body of POST /clips/{id}/headline: the clip's headline text, or
    null to have the LLM write one (pipeline/headline)."""

    model_config = ConfigDict(extra="forbid")

    text: HookText | None = None


class MotionGraphicPick(BaseModel):
    """A motion graphic that the LLM picks for a clip: kind, the text to
    show and a short label under it ("" for none: a name's role, what a
    number counts), and quote, the words of the clip it goes with, as they
    are said (the graphic shows from the first of them)."""

    kind: MotionGraphicKind
    text: str = Field(min_length=1, max_length=MOTION_GRAPHIC_TEXT_MAX)
    label: str = Field(default="", max_length=MOTION_GRAPHIC_TEXT_MAX)
    quote: str = Field(min_length=1, max_length=MOTION_GRAPHIC_QUOTE_MAX)


class MotionGraphicsReply(BaseModel):
    """The LLM's reply with the motion graphics of a clip, in any order
    (none if it says nothing worth one)."""

    items: list[MotionGraphicPick] = Field(max_length=MOTION_GRAPHIC_PICKS_MAX)


class MotionGraphicsApply(BaseModel):
    """The body of POST /clips/{id}/motion-graphics: place at most
    max_items motion graphics (fewer if the text track has no room)."""

    model_config = ConfigDict(extra="forbid")

    max_items: int = Field(default=3, ge=1, le=5)


class ZoomKeyframe(BaseModel):
    """The zoom of a clip's frames at t seconds into the source: scale 1 shows
    the framed clip as it is, 1.15 magnifies it 15% (pipeline/auto_zoom)."""

    t: float
    scale: float = Field(ge=1, le=2)


class Clip(BaseModel):
    """A clip of a project: the segments of the source that it plays, in
    order, and its timeline tracks; cut_ranges are removed [start, end]
    sub-ranges. start and end (read-only) are the source span that the
    segments cover: what v1 stored and the editor still edits."""

    id: int
    project_id: int
    segments: list[SourceSpan] = Field(min_length=1)
    tracks: Timeline
    title: str
    hook_text: str
    description: str
    hashtags: list[str]
    emphasis_words: list[str]
    reason: str
    scores: Scores
    layout: Layout
    caption_template: str
    caption_overrides: list[Word]
    cut_ranges: list[CutRange]
    status: ClipStatus
    output_path: str | None
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    # The fill window's shift, in fractions of its width (-1 left, 1 right).
    crop_offset: float = Field(default=0, ge=-1, le=1)
    framing: Framing = Field(default_factory=Framing)
    # Whether cut_ranges hold the auto cut's jump cuts (pipeline/auto_cut).
    auto_cut: bool = False
    # Whether the render zooms the frames as zoom_keyframes say (auto zoom).
    auto_zoom: bool = False
    zoom_keyframes: list[ZoomKeyframe] = Field(default_factory=list)
    # The clip's scenes as the editor framed them; none: the clip's layout
    # and crop plan throughout.
    scene_reframes: list[SceneReframe] = Field(default_factory=list)
    # Whether the render levels the clip's colours (auto color correction).
    auto_color: bool = False
    # Whether the clip shows word captions; its hook shows either way.
    show_captions: bool = True
    # The result set of the project that the clip belongs to (1: the first
    # processing; each reprompt makes the next one).
    result_set: int = Field(default=1, ge=1)
    transitions: ClipTransitions = Field(default_factory=ClipTransitions)
    # The clip's viral hook over its first seconds (None: none).
    hook: ClipHook | None = None
    # How strongly the render cleans the speech (noise reduction; 0: off).
    enhance: float = Field(default=0, ge=0, le=1)
    # A Pro Edit variant is a clip of its own that points to the clip it was
    # made from (SPEC-v3 0.13); every other clip is an original.
    parent_clip_id: int | None = None
    variant: ClipVariant = "original"

    @model_validator(mode="after")
    def _variant_has_a_parent(self) -> Self:
        if (self.variant == "pro_edit") != (self.parent_clip_id is not None):
            raise ValueError("a pro_edit variant (and only it) has a parent_clip_id")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def start(self) -> float:
        """Where the earliest segment starts, in source seconds (read-only)."""
        return min(start for start, _ in self.segments)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def end(self) -> float:
        """Where the latest segment ends, in source seconds (read-only)."""
        return max(end for _, end in self.segments)


class ClipState(BaseModel):
    """What a version of a clip keeps (SPEC-v2 3.5 versions): every field
    of the clip that an edit changes. Not its status, render, scores or
    result set."""

    segments: list[SourceSpan] = Field(min_length=1)
    tracks: Timeline
    title: str
    hook_text: str
    description: str
    hashtags: list[str]
    emphasis_words: list[str]
    layout: Layout
    caption_template: str
    caption_overrides: list[Word]
    cut_ranges: list[CutRange]
    caption_style: CaptionStyle = Field(default_factory=CaptionStyle)
    crop_offset: float = Field(default=0, ge=-1, le=1)
    framing: Framing = Field(default_factory=Framing)
    auto_cut: bool = False
    auto_zoom: bool = False
    zoom_keyframes: list[ZoomKeyframe] = Field(default_factory=list)
    scene_reframes: list[SceneReframe] = Field(default_factory=list)
    auto_color: bool = False
    show_captions: bool = True
    transitions: ClipTransitions = Field(default_factory=ClipTransitions)
    hook: ClipHook | None = None
    enhance: float = Field(default=0, ge=0, le=1)


# original: the clip before its first edit; edit: the clip after an edit
# (each saved change, so the editor's autosave too); restore: an earlier
# version made current again.
ClipVersionKind = Literal["original", "edit", "restore"]


class ClipVersionInfo(BaseModel):
    """A version of a clip in its history, without its state. number grows
    with each version and is never reused; fields are the ClipState fields
    that differ from the version before it (empty for the original);
    restored_from is the version a restore copied."""

    number: int = Field(ge=1)
    kind: ClipVersionKind
    created_at: datetime
    fields: list[str]
    restored_from: int | None = None


class ClipVersion(ClipVersionInfo):
    """A version of a clip with the clip's state at that version."""

    state: ClipState


class ClipHistory(BaseModel):
    """The undo/redo history of a clip: its versions, oldest first, and the
    number of the one the clip shows (current; 0 before its first edit).
    Undo goes to the version before current, redo to the one after."""

    current: int = Field(ge=0)
    can_undo: bool
    can_redo: bool
    versions: list[ClipVersionInfo]


class CleanupSuggestion(BaseModel):
    """A cut that speech cleanup (polish, SPEC 6.10; pipeline/cleanup,
    SPEC-v2 3.5) suggests for a clip, in seconds of the source: filler
    words (text, with any pause around them), a pause (text "") or a bad
    take (text: its words)."""

    start: float
    end: float
    kind: CleanupKind
    text: str


FillerEntry = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
]


class CleanupOptions(BaseModel):
    """The body of POST /clips/{id}/cleanup/preview: what speech cleanup
    looks for. fillers: the filler words of the list of language (None: the
    transcript's; a language without a list uses English) plus
    extra_fillers; pauses: gaps longer than pause_threshold_s seconds;
    bad_takes: repeated or abandoned sentences, found by the LLM."""

    model_config = ConfigDict(extra="forbid")

    fillers: bool = True
    pauses: bool = True
    pause_threshold_s: float = Field(
        default=CLEANUP_PAUSE_S, ge=CLEANUP_PAUSE_MIN_S, le=CLEANUP_PAUSE_MAX_S
    )
    bad_takes: bool = False
    language: str | None = Field(default=None, min_length=2, max_length=10)
    extra_fillers: list[FillerEntry] = Field(
        default_factory=list, max_length=CLEANUP_EXTRA_FILLERS_MAX
    )


class CleanupPreview(BaseModel):
    """What speech cleanup would remove from a clip, for review: items in
    source order (none that the clip already cuts), and filler_language,
    the code of the filler list it used."""

    filler_language: str
    items: list[CleanupSuggestion]


class SpeechEnhance(BaseModel):
    """The body of PUT /clips/{id}/enhance: how strongly the render cleans the
    clip's speech, 0 (off) to 1 (strongest; pipeline/enhance)."""

    model_config = ConfigDict(extra="forbid")

    strength: float = Field(ge=0, le=1)


class CleanupApply(BaseModel):
    """The body of POST /clips/{id}/cleanup/apply: the items of a preview,
    and the indexes of those the user unchecked, which stay."""

    model_config = ConfigDict(extra="forbid")

    items: list[CleanupSuggestion] = Field(max_length=CLEANUP_ITEMS_MAX)
    unchecked: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_items(self) -> Self:
        """Every item must end after it starts, and every unchecked index
        must be an item's."""
        for index, item in enumerate(self.items):
            if not 0 <= item.start < item.end:
                raise ValueError(f"items.{index} must end after it starts")
        for index in self.unchecked:
            if not 0 <= index < len(self.items):
                raise ValueError(f"unchecked index {index} is not an item's")
        return self


class BadTakePick(BaseModel):
    """A bad take that the LLM finds in a clip: the numbers of its first and
    last word in the numbered words of the prompt (from 0)."""

    first: int = Field(ge=0)
    last: int = Field(ge=0)


class BadTakesReply(BaseModel):
    """The LLM's reply with the bad takes of a clip (none if it has none)."""

    takes: list[BadTakePick] = Field(max_length=BAD_TAKES_MAX)


class ClipText(BaseModel):
    """A clip's title, description and hashtags as the LLM rewrites them
    (POST /clips/{id}/regenerate-text), with ClipCandidate's limits."""

    title: str = Field(max_length=70)
    description: str = Field(max_length=300)
    hashtags: list[Hashtag] = Field(min_length=3, max_length=8)


class WordMark(BaseModel):
    """One word of a clip's captions as the LLM marks it: its number in the
    numbered words that the prompt lists (from 0), whether it is an emphasis
    word, and the emoji that follows it ("" for none)."""

    index: int = Field(ge=0)
    emphasis: bool = False
    emoji: Emoji | Literal[""] = ""


class WordMarks(BaseModel):
    """The words the LLM marks, {"marks": [...]}: the reply to the caption
    emphasis prompt (pipeline/caption_emphasis)."""

    marks: list[WordMark]


# The platforms that the post copy generator writes for.
CopyPlatform = Literal["youtube", "tiktok", "instagram", "facebook"]
PostTone = Literal["casual", "punchy", "professional", "funny"]
PostFormat = Literal["short", "list", "story"]
HashtagChange = Literal["more", "fewer", "none"]


class PostCopy(BaseModel):
    """What a post says on one platform, as the Schedule post form holds
    it: title (empty on platforms whose post has none; the headline then
    starts the caption), caption (the description) and hashtags without
    "#"."""

    title: str
    caption: str
    hashtags: list[str]


class PostCopyRequest(BaseModel):
    """The body of POST /clips/{id}/post-copy: write the post of the clip on
    platform. Without options the whole copy is new. tone and format
    rewrite the title and caption (current says what they are now);
    hashtags (more, fewer, none) changes only the hashtags. account_id is
    the account the post is for: its always_hashtags are added to the
    always-included ones."""

    model_config = ConfigDict(extra="forbid")

    platform: CopyPlatform
    tone: PostTone | None = None
    format: PostFormat | None = None
    hashtags: HashtagChange | None = None
    current: PostCopy | None = None
    account_id: int | None = None

    @model_validator(mode="after")
    def _current_for_options(self) -> Self:
        """A rewrite needs the copy it starts from."""
        rewrite = (self.tone, self.format, self.hashtags)
        if any(rewrite) and self.current is None:
            raise ValueError("current is required with tone, format or hashtags")
        return self


def _reply_tags(values: list[str]) -> list[str]:
    """Strip "#" and spaces from each hashtag of an LLM reply, drop empty
    and repeated ones (the first spelling stays), keep the order."""
    seen: dict[str, str] = {}
    for value in values:
        tag = re.sub(r"[#\s]+", "", value)
        if tag:
            seen.setdefault(tag.lower(), tag)
    return list(seen.values())


class PostTextReply(BaseModel):
    """The LLM's headline and description of a post (limits are applied to
    the platform afterwards, by cutting)."""

    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=10_000)


class PostTagsReply(BaseModel):
    """The LLM's hashtags of a post."""

    hashtags: Annotated[list[str], AfterValidator(_reply_tags)] = Field(max_length=50)


class PostCopyReply(PostTextReply, PostTagsReply):
    """The LLM's headline, description and hashtags of a post."""


class ThumbnailFrame(BaseModel):
    """The body of POST /clips/{id}/thumbnail: the moment of the clip's
    rendered video, in seconds from its start, to use as the cover."""

    model_config = ConfigDict(extra="forbid")

    time_s: float = Field(ge=0)


class ThumbnailApply(BaseModel):
    """The body of POST /clips/{id}/thumbnail/apply: the cover (an image
    asset) for every draft and queued post of the clip."""

    model_config = ConfigDict(extra="forbid")

    asset_id: int


class ClipPatch(BaseModel):
    """The body of PATCH /clips/{id}: the fields to change (unset or null
    fields are kept). start and end move the clip's span: where its earliest
    segment in the source starts and its latest one ends. The API also
    checks the result: start < end within the source, cut_ranges inside the
    clip, a known caption template, scenes that cover the clip in order (or
    none)."""

    model_config = ConfigDict(extra="forbid")

    start: float | None = Field(default=None, ge=0)
    end: float | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, max_length=70)
    hook_text: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=300)
    hashtags: list[Hashtag] | None = Field(default=None, max_length=8)
    layout: Layout | None = None
    caption_template: str | None = None
    caption_overrides: list[Word] | None = None
    caption_style: CaptionStyle | None = None
    crop_offset: float | None = Field(default=None, ge=-1, le=1)
    framing: Framing | None = None
    cut_ranges: list[CutRange] | None = None
    auto_cut: bool | None = None
    auto_zoom: bool | None = None
    zoom_keyframes: list[ZoomKeyframe] | None = None
    auto_color: bool | None = None
    show_captions: bool | None = None
    scene_reframes: list[SceneReframe] | None = None
    transitions: ClipTransitions | None = None


class SectionSpan(BaseModel):
    """The body of PUT /clips/{id}/sections/{index} (SPEC-v2 3.5 trim or
    extend a section): its new start and end in seconds of the source. The
    API clamps them to the source and to the sections next to it there."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(ge=0)
    end: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        """Require start < end."""
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class SectionAdd(SectionSpan):
    """The body of POST /clips/{id}/sections: a part of the source to add
    to the clip as a section, played at index of the clip's sections (0:
    first; null: last). It may not overlap another section."""

    index: int | None = Field(default=None, ge=0)


class SectionSplit(BaseModel):
    """The body of POST /clips/{id}/sections/split: split the section that
    plays the source at at seconds into two at that time."""

    model_config = ConfigDict(extra="forbid")

    at: float = Field(gt=0)


class SectionOrder(BaseModel):
    """The body of POST /clips/{id}/sections/reorder: the clip's sections'
    current indices in their new play order (each index once)."""

    model_config = ConfigDict(extra="forbid")

    order: list[int] = Field(min_length=1)


class ClipSplit(BaseModel):
    """The body of POST /clips/{id}/split: split the clip in two at at
    seconds of the source (inside one of its sections, or on the edge between
    two); the clip keeps what plays before, a new clip gets what plays
    after."""

    model_config = ConfigDict(extra="forbid")

    at: float = Field(gt=0)


# How long after its publication a campaign creator's video is a fresh upload.
FRESH_UPLOAD_HOURS = 48


class Project(BaseModel):
    """A source video and the settings used to process it."""

    id: int
    source_url: str | None
    source_path: str
    title: str
    duration: float
    thumbnail_path: str
    settings: ProcessingSettings
    # A project's status mirrors the status of its processing job.
    status: JobStatus
    created_at: datetime
    # None until the owner sets it: v1 projects migrate with None.
    source_rights: SourceRights | None = None
    credit_line: str = ""
    campaign_id: int | None = None
    # When the source video was published, if Auto Import found it.
    source_published_at: datetime | None = None
    # The current result set: the clips of that set are the project's clips;
    # the lower sets are the previous results of its reprompts.
    result_set: int = Field(default=1, ge=1)
    # The progress of the project's current process or reprompt job across all
    # of its steps, and the seconds it still needs (None while unknown).
    overall_progress: UnitInterval = 0.0
    eta_seconds: float | None = Field(default=None, ge=0)
    # When the project was first opened after it was done; None: the card
    # shows a "New" badge.
    opened_at: datetime | None = None
    # When the storage manager archived the project (its source video and
    # work files deleted, rendered clips kept); None if it is not archived.
    archived_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rights_set(self) -> bool:
        """Whether the source rights are set; publishing needs them (read-only)."""
        return self.source_rights is not None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fresh_upload(self) -> bool:
        """Whether this is a campaign project of a source published within
        FRESH_UPLOAD_HOURS (the "fresh upload" badge; read-only)."""
        published = self.source_published_at
        if self.campaign_id is None or published is None:
            return False
        if published.tzinfo is None:
            published = published.replace(tzinfo=UTC)
        age = datetime.now(UTC) - published
        return age <= timedelta(hours=FRESH_UPLOAD_HOURS)


class ProjectCreate(BaseModel):
    """The body of POST /projects: a video URL, how to process it and, if the
    owner says so now, why they may use it (SPEC-v2 1.6)."""

    url: HttpUrl
    settings: ProcessingSettings = Field(default_factory=ProcessingSettings)
    source_rights: SourceRights | None = None
    credit_line: str = Field(default="", max_length=CREDIT_LINE_MAX)


class RepromptRequest(BaseModel):
    """The body of POST /projects/{id}/reprompt: the new prompt-to-clip
    request (not blank), applied to the project's existing transcript."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=PROMPT_MAX)

    @model_validator(mode="after")
    def _not_blank(self) -> Self:
        self.prompt = " ".join(self.prompt.split())
        if not self.prompt:
            raise ValueError("prompt must not be blank")
        return self


class ChapterDraft(BaseModel):
    """A topic chapter as the LLM proposes it (pipeline/chapters): its span in
    seconds from the start of the video, a title and a one-line summary."""

    start: float = Field(ge=0)
    end: float = Field(gt=0)
    title: str = Field(min_length=1, max_length=CHAPTER_TITLE_MAX)
    summary: str = Field(default="", max_length=CHAPTER_SUMMARY_MAX)


class ChapterReply(BaseModel):
    """The reply the chapters prompt asks the LLM for: {"chapters": [...]}."""

    chapters: list[ChapterDraft]


class Chapter(BaseModel):
    """A topic of a project's video: sentences from start to end seconds.

    id counts from 1. The chapters of a project follow each other without gap
    or overlap and each one starts at the start of a sentence.
    """

    id: int = Field(ge=1)
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    title: str
    summary: str


class ChapterList(BaseModel):
    """The chapters of a project as {"chapters": [...]}: chapters.json."""

    chapters: list[Chapter]


class TopicClipRequest(BaseModel):
    """The body of POST /projects/{id}/clip-by-topic: the ids of the chapters
    to clip (at least one, each once) and, optionally, a prompt-to-clip
    request that applies within them."""

    model_config = ConfigDict(extra="forbid")

    chapters: list[int] = Field(min_length=1)
    prompt: str | None = Field(default=None, max_length=PROMPT_MAX)

    @model_validator(mode="after")
    def _tidy(self) -> Self:
        self.prompt = " ".join((self.prompt or "").split()) or None
        self.chapters = sorted(set(self.chapters))
        return self


class ProjectPatch(BaseModel):
    """The body of PATCH /projects/{id}: the brand template of the project's
    clips (null: none), its source rights (null: unset), credit line and
    title (the owner's name for it; not blank).

    Only the fields that are sent change; at least one must be sent.
    """

    model_config = ConfigDict(extra="forbid")

    brand_template_id: int | None = None
    source_rights: SourceRights | None = None
    credit_line: str = Field(default="", max_length=CREDIT_LINE_MAX)
    title: str = Field(default="", max_length=PROJECT_TITLE_MAX)

    @model_validator(mode="after")
    def _something_to_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(
                "send brand_template_id, source_rights, credit_line or title"
            )
        if "title" in self.model_fields_set and not self.title.strip():
            raise ValueError("title must not be blank")
        return self


class ZoomOutRequest(BaseModel):
    """The body of PUT /projects/{id}/zoom-out: the zoom-out moments
    intensity to save for the project and apply to its clips."""

    model_config = ConfigDict(extra="forbid")

    intensity: ZoomOutIntensity


class CameraMotionRequest(BaseModel):
    """The body of PUT /projects/{id}/camera-motion: the camera motion to
    save for the project and apply to its clips' crop plans."""

    model_config = ConfigDict(extra="forbid")

    camera_motion: CameraMotion


class CameraMotionResult(BaseModel):
    """The answer to PUT /projects/{id}/camera-motion: the project with the
    saved camera motion and the ids of the clips whose crop plans were
    tracked again (render them to apply the change)."""

    project: Project
    clip_ids: list[int]


class ZoomOutResult(BaseModel):
    """The answer to PUT /projects/{id}/zoom-out: the project with the
    saved intensity and the ids of the clips whose scenes were planned
    again (render them to apply the change)."""

    project: Project
    clip_ids: list[int]


class Job(BaseModel):
    """A queued unit of work; progress is a fraction from 0 to 1. The worker
    pool runs the queued job with the highest priority first (then the
    oldest); attempts counts the times a worker started it."""

    id: int
    project_id: int
    clip_id: int | None
    kind: JobKind
    step: str
    progress: UnitInterval
    status: JobStatus
    error: str | None
    log_path: str
    priority: int
    attempts: int = Field(ge=0)
    # The progress across all steps of the job (each step weighs its share,
    # job_progress) and the smoothed seconds it still needs (None while unknown).
    overall_progress: UnitInterval = 0.0
    eta_seconds: float | None = Field(default=None, ge=0)


class BrandTemplate(BaseModel):
    """Branding applied to rendered clips."""

    id: int
    name: str = Field(min_length=1)
    logo_path: str
    logo_position: LogoPosition
    logo_opacity: UnitInterval
    font: str
    primary_color: HexColor
    intro_path: str | None
    outro_path: str | None


class Asset(BaseModel):
    """A file in the asset library with its license (SPEC-v2 1.3, 4). The
    fields after tags describe an audio asset (SPEC-v3 5): its tempo (bpm),
    musical key, integrated loudness, energy over time (one value per
    second, 0 to 1), category (whoosh, impact, riser, ...), mood and when it
    was downloaded; they are None for an asset that was not analyzed or is
    not audio."""

    id: int
    kind: AssetKind
    path: str = Field(min_length=1)
    license: str = Field(min_length=1)
    attribution: str
    source_url: str | None
    tags: list[str]
    bpm: float | None = Field(default=None, gt=0)
    key: str | None = Field(default=None, min_length=1)
    loudness_lufs: float | None = None
    energy_curve: list[float] | None = None
    category: str | None = Field(default=None, min_length=1)
    mood: str | None = Field(default=None, min_length=1)
    downloaded_at: datetime | None = None


StockSource = Literal["pexels", "pixabay"]


class StockClip(BaseModel):
    """A stock video found by a provider (SPEC-v2 3.6) that can be downloaded
    as B-roll: provider_id is the provider's own id, preview_url a still or
    clip for showing results, download_url the file that gets stored (the
    best fit for the requested size). license and attribution are what the
    asset keeps; creator_url is None if the provider has no profile page."""

    provider: StockSource
    provider_id: str = Field(min_length=1)
    page_url: str = Field(min_length=1)
    preview_url: str | None
    download_url: str = Field(min_length=1)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    duration_s: float = Field(ge=0)
    creator: str
    creator_url: str | None
    tags: list[str]
    license: str = Field(min_length=1)
    attribution: str


class StockProviderStatus(BaseModel):
    """Whether a stock provider can be used: when it cannot (no API key),
    message says which setting to fill in."""

    provider: StockSource
    label: str
    enabled: bool
    message: str


# The most B-roll spots of one clip, and of search words per spot.
BROLL_SPOTS_MAX = 10
BROLL_KEYWORDS_MAX = 4
BROLL_KEYWORD_MAX = 40


class BrollPick(BaseModel):
    """A sentence of a clip that the LLM wants B-roll on: its number in the
    numbered sentences of the prompt (from 0) and the words to search stock
    video with."""

    sentence: int = Field(ge=0)
    keywords: list[
        Annotated[
            str,
            StringConstraints(
                strip_whitespace=True, min_length=1, max_length=BROLL_KEYWORD_MAX
            ),
        ]
    ] = Field(min_length=1, max_length=BROLL_KEYWORDS_MAX)


class BrollReply(BaseModel):
    """The LLM's reply with the B-roll spots of a clip (none if it needs
    none)."""

    spots: list[BrollPick] = Field(max_length=BROLL_SPOTS_MAX)


class BrollSpotsOptions(BaseModel):
    """The body of POST /clips/{id}/broll/spots: how many spots to find at
    most, how the B-roll will show (it picks the shape of the stock videos
    found: the clip's for a cutaway, landscape for picture-in-picture) and
    the stock provider to search (None: the first one with an API key)."""

    model_config = ConfigDict(extra="forbid")

    max_spots: int = Field(default=4, ge=1, le=BROLL_SPOTS_MAX)
    mode: BrollMode = "cutaway"
    provider: StockSource | None = None


class BrollSpot(BaseModel):
    """A spot of a clip for B-roll, to review: sentence (its number) whose
    text is said from start to end seconds of the rendered clip (the times a
    B-roll item there gets), the LLM's keywords, query (what was searched)
    and the stock videos found (results), or error if the search failed."""

    sentence: int = Field(ge=0)
    text: str
    start: float = Field(ge=0)
    end: float
    keywords: list[str]
    query: str
    results: list[StockClip]
    error: str | None = None


class BrollSource(BaseModel):
    """What a B-roll item plays: a stock video found by a search (stock,
    downloaded into the asset library) or a video or image of the asset
    library (asset_id); exactly one of them."""

    model_config = ConfigDict(extra="forbid")

    stock: StockClip | None = None
    asset_id: int | None = None

    @model_validator(mode="after")
    def _check_one(self) -> Self:
        """Reject a body with neither or both sources."""
        if (self.stock is None) == (self.asset_id is None):
            raise ValueError("give exactly one of stock and asset_id")
        return self


class BrollInsert(BrollSource):
    """The body of POST /clips/{id}/broll: put source on the clip's B-roll
    track from start to end seconds of the rendered clip (cut short if the
    video is shorter) as a full-screen cutaway or a picture-in-picture
    (x, y, width: BrollProps)."""

    start: float = Field(ge=0)
    end: float
    mode: BrollMode = "cutaway"
    x: UnitInterval = 0.5
    y: UnitInterval = 0.3
    width: float = Field(default=0.8, gt=0, le=1)

    @model_validator(mode="after")
    def _check_times(self) -> Self:
        """Reject an end that is not after start."""
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class FontFile(BaseModel):
    """A font of the asset library (SPEC-v2 3.4): names are what a caption
    style or brand template calls it (family and full name); bundled fonts
    come with ClipForge, the others were uploaded."""

    asset: Asset
    names: list[str]
    bundled: bool


class MusicTrack(BaseModel):
    """A track of the music library (SPEC-v2 3.5): a bundled loop
    (assets/music, with its title and mood tags) or a music file uploaded
    to the media library (its file name and the owner's tags). duration is
    the file's length in seconds (None if ffprobe cannot read it)."""

    asset: Asset
    title: str
    duration: float | None
    bundled: bool
    tags: list[str]


class SfxSound(BaseModel):
    """A sound effect of the bundled pack (assets/sfx; pipeline/sfx): its
    library asset, title, tags to search by and length in seconds (None if
    ffprobe cannot read the file)."""

    asset: Asset
    title: str
    duration: float | None
    tags: list[str]


# The sounds that one auto SFX run places, and the tags the LLM gives each.
SFX_ITEMS_MAX, SFX_TAGS_MAX = 8, 4


class SfxPick(BaseModel):
    """A sound effect that the LLM wants at a moment of a clip: its number in
    the numbered moments of the prompt (from 0) and tags that describe the
    sound (searched in the pack)."""

    moment: int = Field(ge=0)
    tags: list[str] = Field(min_length=1, max_length=SFX_TAGS_MAX)


class SfxReply(BaseModel):
    """The LLM's reply with the sound effects of a clip (none if it needs
    none)."""

    sounds: list[SfxPick] = Field(max_length=SFX_ITEMS_MAX)


class AutoSfxOptions(BaseModel):
    """The body of POST /clips/{id}/auto-sfx: how many sounds to place at
    most."""

    model_config = ConfigDict(extra="forbid")

    max_items: int = Field(default=5, ge=1, le=SFX_ITEMS_MAX)


# What marks an asset as a media library upload, and the tags that no one sets.
MEDIA_LIBRARY_TAG = "media-library"
RESERVED_MEDIA_TAGS = frozenset({MEDIA_LIBRARY_TAG, "uploaded", "bundled"})
MEDIA_TAGS_MAX = 20
MEDIA_TAG_MAX = 30


def _tidy_media_tags(tags: list[str]) -> list[str]:
    """Return tags in lower case with single spaces, without empty or repeated
    ones (the order stays); reject a reserved or too long tag and more than
    MEDIA_TAGS_MAX tags."""
    tidy: dict[str, None] = {}
    for tag in tags:
        name = " ".join(tag.lower().split())
        if len(name) > MEDIA_TAG_MAX:
            raise ValueError(f"a tag is at most {MEDIA_TAG_MAX} characters")
        if name in RESERVED_MEDIA_TAGS:
            raise ValueError(f"the tag {name!r} is reserved")
        if name:
            tidy[name] = None
    if len(tidy) > MEDIA_TAGS_MAX:
        raise ValueError(f"at most {MEDIA_TAGS_MAX} tags")
    return list(tidy)


MediaTags = Annotated[list[str], AfterValidator(_tidy_media_tags)]


class MediaMeta(BaseModel):
    """What the media library keeps of an uploaded file, next to it: the name
    the client gave, the MIME type from its first bytes, its size, what
    ffprobe read (duration for video and audio, size in pixels for video and
    images) and the file name of its thumbnail, if it has one."""

    name: str
    mime: str
    size_bytes: int
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    thumbnail: str | None = None


class MediaItem(BaseModel):
    """A file of the media library (SPEC-v2 3.5): an image, logo, video or
    audio asset the owner uploaded. tags are the owner's; used_in_clips lists
    the clips whose timeline plays the file, and a file that a clip uses
    cannot be deleted."""

    asset: Asset
    tags: list[str]
    name: str
    mime: str
    size_bytes: int
    duration: float | None
    width: int | None
    height: int | None
    has_thumbnail: bool
    used_in_clips: list[int]


class MediaUpdate(BaseModel):
    """The changes of a media library file: send what changes."""

    model_config = ConfigDict(extra="forbid")

    tags: MediaTags | None = None
    license: str | None = Field(default=None, min_length=1, max_length=200)
    attribution: str | None = Field(default=None, max_length=500)


# The most vocabulary terms and corrections, and the longest of each.
MAX_VOCABULARY_ENTRIES = 100
VOCABULARY_TEXT_MAX = 100


def _tidy_phrase(text: str) -> str:
    """Return text on one line with single spaces; every space-separated
    piece must have a letter or digit (a vocabulary phrase is matched by
    those)."""
    phrase = " ".join(text.split())
    if not phrase or not all(re.search(r"\w", piece) for piece in phrase.split()):
        raise ValueError(f"{text!r} must be words with letters or digits")
    return phrase


VocabularyPhrase = Annotated[
    str, Field(max_length=VOCABULARY_TEXT_MAX), AfterValidator(_tidy_phrase)
]


class Vocabulary(BaseModel):
    """The brand vocabulary (SPEC-v2 3.4): terms Whisper is told to expect
    (its hotwords), and corrections {heard: correct} that every transcript
    gets after transcription. A correction matches whole words, any case."""

    terms: list[VocabularyPhrase] = Field(
        default_factory=list, max_length=MAX_VOCABULARY_ENTRIES
    )
    corrections: dict[VocabularyPhrase, VocabularyPhrase] = Field(
        default_factory=dict, max_length=MAX_VOCABULARY_ENTRIES
    )

    @field_validator("terms")
    @classmethod
    def _terms_once(cls, terms: list[str]) -> list[str]:
        """Keep the first of terms that differ only in case."""
        first: dict[str, str] = {}
        for term in terms:
            first.setdefault(term.casefold(), term)
        return list(first.values())

    @field_validator("corrections")
    @classmethod
    def _corrections_once(cls, corrections: dict[str, str]) -> dict[str, str]:
        """Reject two corrections of the same words in different case."""
        heard = [phrase.casefold() for phrase in corrections]
        if len(set(heard)) != len(heard):
            raise ValueError("a correction is given twice (case aside)")
        return corrections


# The most custom censor words, and the longest.
MAX_CENSOR_WORDS = 500
CENSOR_WORD_MAX = 50
# A censor list entry: a word (letters, digits, ' and -), maybe ending in *.
CENSOR_ENTRY = re.compile(r"^[\w'’-]+\*?$")


def _censor_entry(text: str) -> str:
    """Return the censor list entry text, trimmed and in lowercase; it must
    be one word, which a trailing * makes a prefix ("fuck*")."""
    entry = text.strip().casefold()
    if not CENSOR_ENTRY.match(entry) or not re.search(r"\w", entry):
        raise ValueError(f"{text!r} must be one word, maybe ending in *")
    return entry


CensorEntry = Annotated[
    str, Field(max_length=CENSOR_WORD_MAX), AfterValidator(_censor_entry)
]


class CensorWords(BaseModel):
    """The custom censor list (SPEC-v2 3.4), censored with the default list
    of the captions' language: whole words, any case; an entry ending in *
    censors every word that starts with it."""

    model_config = ConfigDict(extra="forbid")

    words: list[CensorEntry] = Field(default_factory=list, max_length=MAX_CENSOR_WORDS)

    @field_validator("words")
    @classmethod
    def _words_once(cls, words: list[str]) -> list[str]:
        """Keep the first of each entry."""
        return list(dict.fromkeys(words))


class ReplaceRequest(BaseModel):
    """The body of POST /projects/{id}/replace-everywhere: change the words
    find (whole words, any case) into replace in the project's transcript and
    clips; remember also adds it to the vocabulary's corrections."""

    model_config = ConfigDict(extra="forbid")

    find: VocabularyPhrase
    replace: VocabularyPhrase
    remember: bool = False


class ReplaceResult(BaseModel):
    """What replace-everywhere changed: the places in the transcript, and
    the clips whose texts or caption words changed."""

    transcript_matches: int
    clips_changed: int


class UsageRecord(BaseModel):
    """A measured use of compute or a paid service (SPEC-v2 2.4): units of
    its kind (seconds, tokens, calls) and the cost in USD if it is paid.
    project_id is None for use outside a project."""

    id: int
    project_id: int | None
    kind: str = Field(min_length=1)
    units: float = Field(ge=0)
    cost_usd: float | None = Field(ge=0)
    at: datetime


def _tags(values: list[str]) -> list[str]:
    """Strip each hashtag or @mention, drop empty and repeated ones (the
    first spelling stays), keep the order."""
    seen: dict[str, str] = {}
    for value in values:
        tidy = value.strip()
        if tidy.lstrip("#@"):
            seen.setdefault(tidy.lower(), tidy)
    return list(seen.values())


class CampaignCreate(BaseModel):
    """What the owner enters for a clipping campaign (SPEC-v2 3.18): all of
    it comes from forms and pasted text, nothing is fetched from a campaign
    board. required_hashtags are stored without "#". rate_per_1k_usd is
    None for an unpaid or unknown rate; monetization_allowed_elsewhere is
    None while unknown; end_date (None: open-ended) is the last day that the
    autopilot safety stop lets the campaign run (SPEC-v2 3.19). The
    permission source URL is the page that shows the owner may clip the
    creator; the screenshot is uploaded on its own."""

    name: str = Field(min_length=1, max_length=200)
    creator_name: str = Field(default="", max_length=200)
    source_channel_urls: list[HttpUrl] = Field(default_factory=list, max_length=50)
    platform_board: CampaignBoard = "other"
    campaign_url: HttpUrl | None = None
    permission_source_url: HttpUrl | None = None
    badge: CampaignBadge = "open"
    rate_per_1k_usd: float | None = Field(default=None, ge=0)
    budget_note: str = Field(default="", max_length=CAMPAIGN_TEXT_MAX)
    allowed_platforms: list[CampaignPlatform] = Field(default_factory=list)
    required_hashtags: list[str] = Field(default_factory=list, max_length=30)
    required_credit_line: str = Field(default="", max_length=CREDIT_LINE_MAX)
    required_tags_mentions: list[str] = Field(default_factory=list, max_length=30)
    min_duration_s: float | None = Field(default=None, gt=0)
    max_duration_s: float | None = Field(default=None, gt=0)
    banned_content_notes: str = Field(default="", max_length=CAMPAIGN_TEXT_MAX)
    monetization_allowed_elsewhere: bool | None = None
    submission_instructions: str = Field(default="", max_length=CAMPAIGN_TEXT_MAX)
    status: CampaignStatus = "active"
    notes: str = Field(default="", max_length=CAMPAIGN_TEXT_MAX)
    end_date: date | None = None
    # The caption template that applying the campaign gives a project and
    # its clips (None: they keep theirs); the API checks that it exists.
    caption_template: str | None = Field(default=None, min_length=1, max_length=60)
    # Whether the campaign's rules allow heavily edited clips (Pro Edit,
    # SPEC-v3 6); the owner reads this from the rules, so it starts unknown.
    allow_heavy_edits: HeavyEditsAllowed = "unknown"

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()

    @field_validator("allowed_platforms")
    @classmethod
    def _platforms_once(cls, values: list[CampaignPlatform]) -> list[CampaignPlatform]:
        return list(dict.fromkeys(values))

    @field_validator("required_hashtags", mode="before")
    @classmethod
    def _hashtags_without_hash(cls, values: Any) -> Any:
        if not isinstance(values, list):
            return values
        return _tags(
            [v.strip().lstrip("#") if isinstance(v, str) else v for v in values]
        )

    @field_validator("required_tags_mentions")
    @classmethod
    def _mentions_tidy(cls, values: list[str]) -> list[str]:
        return _tags(values)

    @model_validator(mode="after")
    def _duration_range(self) -> Self:
        low, high = self.min_duration_s, self.max_duration_s
        if low is not None and high is not None and low > high:
            raise ValueError("min_duration_s must not be over max_duration_s")
        return self


class _CampaignSaved(BaseModel):
    """What the server keeps of a campaign besides the owner's entries; it
    comes first in Campaign's fields."""

    id: int
    permission_screenshot_asset_id: int | None
    permission_checked_at: datetime | None


class Campaign(CampaignCreate, _CampaignSaved):
    """A clipping campaign (SPEC-v2 3.18). The server sets
    permission_checked_at when the permission source URL or the screenshot
    (an Asset) is saved; permission_complete is true once the URL, the
    screenshot and the date are all there: publishing for a project of the
    campaign is blocked before (read-only)."""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def permission_complete(self) -> bool:
        """Whether the permission evidence is complete (read-only)."""
        return (
            bool(self.permission_source_url)
            and self.permission_screenshot_asset_id is not None
            and self.permission_checked_at is not None
        )


class CampaignPatch(CampaignCreate):
    """The body of PATCH /campaigns/{id}: only the fields that are sent
    change (null clears a nullable field); at least one must be sent."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=200)

    @model_validator(mode="after")
    def _something_to_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("send at least one campaign field")
        return self


# The rules that a clip must pass before it is published for a campaign
# (SPEC-v2 3.18, campaign_rules); source_rights also applies without one.
CampaignRule = Literal[
    "campaign_status",
    "permission",
    "source_rights",
    "min_duration",
    "max_duration",
    "hashtags",
    "credit_line",
    "mentions",
    "platform",
]


class RuleResult(BaseModel):
    """Whether a clip passes one campaign rule; detail says what was found
    or what the owner must fix."""

    rule: CampaignRule
    passed: bool
    detail: str


class CampaignCheck(BaseModel):
    """The rule checker's results for a clip (published on platform, or on
    any of the campaign's platforms when None); campaign_id is None for a
    project without a campaign, which only has the source_rights rule."""

    clip_id: int
    campaign_id: int | None
    platform: SocialPlatform | None
    results: list[RuleResult]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def passed(self) -> bool:
        """Whether every rule passes: publishing is blocked otherwise
        (read-only)."""
        return all(result.passed for result in self.results)


class ProjectCampaign(BaseModel):
    """The body of PUT /projects/{id}/campaign: the campaign whose preset the
    project and its clips get (null: the project leaves its campaign and
    keeps its settings)."""

    model_config = ConfigDict(extra="forbid")

    campaign_id: int | None


class SocialAccount(BaseModel):
    """A social account the owner connected with the platform's OAuth sign-in
    (SPEC-v2 3.10, 4); a platform may have several. token_ref names the
    account's token in the encrypted token store (the token never enters the
    database); scopes are the ones the platform granted; restrictions are
    the platform's limits on this account or app that the UI shows (e.g.
    "unaudited app: posts are private"). is_default marks the account that
    a one-click post uses on its platform (one per platform); avatar_url is
    the picture the platform gave at sign-in; always_hashtags are the hashtags
    (without "#") that every generated post to the account carries."""

    id: int
    platform: SocialPlatform
    external_id: str = Field(min_length=1)
    display_name: str
    token_ref: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    scopes: list[str]
    connected_at: datetime
    restrictions: list[str]
    is_default: bool = False
    avatar_url: str | None = None
    always_hashtags: list[str] = Field(default_factory=list)


class AccountHashtags(BaseModel):
    """The body of PUT /accounts/{id}/hashtags: the hashtags (without "#")
    that every generated post to the account carries, besides the global
    always_hashtags setting and the campaign's required hashtags."""

    model_config = ConfigDict(extra="forbid")

    always_hashtags: Annotated[
        list[str], AfterValidator(clean_tags), Field(max_length=30)
    ]


class Post(BaseModel):
    """A clip posted (or to be posted) to one social account (SPEC-v2 3.10,
    4). payload holds the platform's post fields (title, caption, privacy,
    ...). status moves draft -> queued -> uploading -> published | failed |
    canceled; a queued post missed while the app was off may be skipped
    (clipforge.posts has the legal moves); attempts counts the
    uploads started since it was last queued, attempted_at is when the
    latest one started and next_attempt_at holds a queued post back until
    then (retry backoff, rate limit, quota). account_id is None once its
    account was disconnected (the post's history stays)."""

    id: int
    clip_id: int
    account_id: int | None
    platform: SocialPlatform
    payload: dict[str, Any]
    thumbnail_asset_id: int | None
    scheduled_at: datetime | None
    status: PostStatus
    external_post_id: str | None
    url: str | None
    error: str | None
    attempts: int = Field(ge=0)
    attempted_at: datetime | None = None
    next_attempt_at: datetime | None = None


SubmissionStatus = Literal["not_submitted", "submitted", "approved", "rejected", "paid"]
SUBMISSION_NOTES_MAX = 2000


class Submission(BaseModel):
    """The owner's record of submitting one published post on the board of
    its campaign (SPEC-v2 3.18); the owner submits by hand and ticks it
    here. Made (not_submitted) when the published post is first listed.
    submitted_at is when it was ticked; approved_views and payout_usd are
    what the campaign board reported, entered by the owner; answered_at is
    when they were last entered. campaign_id is None once its campaign was
    deleted (the record stays)."""

    id: int
    post_id: int
    campaign_id: int | None
    submitted_at: datetime | None = None
    status: SubmissionStatus = "not_submitted"
    approved_views: int | None = Field(default=None, ge=0)
    payout_usd: float | None = Field(default=None, ge=0)
    notes: str = Field(default="", max_length=SUBMISSION_NOTES_MAX)
    answered_at: datetime | None = None


class SubmissionView(Submission):
    """A submission with what the tracker shows of its post and campaign:
    the post's platform, URL and clip, the campaign's name, and copy_text,
    the post URL with the campaign's required information, ready to paste
    into the campaign board (read-only)."""

    platform: SocialPlatform
    post_url: str
    clip_id: int
    clip_title: str
    campaign_name: str | None
    copy_text: str


class SubmissionPatch(BaseModel):
    """The body of PATCH /submissions/{id}: the fields that are sent change
    (null clears approved_views, payout_usd; status moves along
    clipforge.submissions.TRANSITIONS, 409 otherwise); at least one."""

    model_config = ConfigDict(extra="forbid")

    status: SubmissionStatus | None = None
    approved_views: int | None = Field(default=None, ge=0)
    payout_usd: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=SUBMISSION_NOTES_MAX)

    @model_validator(mode="after")
    def _something_to_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("send at least one submission field")
        if "status" in self.model_fields_set and self.status is None:
            raise ValueError("status must not be null")
        if "notes" in self.model_fields_set and self.notes is None:
            raise ValueError("notes must not be null")
        return self


YouTubePrivacy = Literal["public", "unlisted", "private"]
YOUTUBE_TITLE_MAX = 100


class YouTubePostOptions(BaseModel):
    """The payload of a YouTube post (SPEC-v2 3.10). title, description and
    tags default to the clip's title, description + hashtags and hashtags;
    category_id is a YouTube video category ("22": People & Blogs). A
    public post with a future scheduled_at is uploaded private with
    YouTube's publishAt; made_for_kids and synthetic_media are the
    channel owner's declarations (child-directed; realistic altered or
    synthetic content). Keys of other platforms are ignored."""

    title: str | None = Field(default=None, max_length=YOUTUBE_TITLE_MAX)
    description: str | None = None
    tags: list[str] | None = None
    category_id: str = Field(default="22", pattern=r"^[0-9]{1,4}$")
    privacy: YouTubePrivacy = "public"
    made_for_kids: bool = False
    synthetic_media: bool = False
    notify_subscribers: bool = True


TikTokPrivacy = Literal[
    "PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"
]
# TikTok counts the caption in UTF-16 code units.
TIKTOK_CAPTION_MAX = 2200


class TikTokPostOptions(BaseModel):
    """The payload of a TikTok post (SPEC-v2 3.10, TikTok's Direct Post
    rules). privacy_level has no default: the user picks one of the
    account's options (unaudited apps: SELF_ONLY only). Comments, Duets
    and Stitches stay off unless allowed. caption defaults to the clip's
    title + hashtags; cover_timestamp_ms picks the cover frame.
    brand_organic (promotes the creator's own business) and branded_content
    (paid partnership, never private) are the commercial content
    disclosure; ai_generated labels AI-generated content. Keys of other
    platforms are ignored."""

    caption: str | None = None
    privacy_level: TikTokPrivacy | None = None
    allow_comment: bool = False
    allow_duet: bool = False
    allow_stitch: bool = False
    cover_timestamp_ms: int | None = Field(default=None, ge=0)
    brand_organic: bool = False
    branded_content: bool = False
    ai_generated: bool = False

    @model_validator(mode="after")
    def _branded_content_is_not_private(self) -> Self:
        """Branded content cannot be posted SELF_ONLY (TikTok's rule)."""
        if self.branded_content and self.privacy_level == "SELF_ONLY":
            raise ValueError("branded content cannot be private (SELF_ONLY)")
        return self


INSTAGRAM_CAPTION_MAX = 2200
INSTAGRAM_HASHTAGS_MAX = 30
INSTAGRAM_MENTIONS_MAX = 20
INSTAGRAM_COLLABORATORS_MAX = 3
InstagramTrialStrategy = Literal["MANUAL", "SS_PERFORMANCE"]


def instagram_caption_problem(caption: str) -> str | None:
    """Return why Instagram would refuse caption (over 2200 characters, 30
    hashtags or 20 @ tags), or None."""
    if len(caption) > INSTAGRAM_CAPTION_MAX:
        return f"the caption has more than {INSTAGRAM_CAPTION_MAX} characters"
    if len(re.findall(r"(?<![\w#])#\w", caption)) > INSTAGRAM_HASHTAGS_MAX:
        return f"the caption has more than {INSTAGRAM_HASHTAGS_MAX} hashtags"
    if len(re.findall(r"(?<![\w@])@[\w.]", caption)) > INSTAGRAM_MENTIONS_MAX:
        return f"the caption has more than {INSTAGRAM_MENTIONS_MAX} @ tags"
    return None


class InstagramPostOptions(BaseModel):
    """The payload of an Instagram Reels post (SPEC-v2 3.10, Instagram's
    content publishing rules). caption defaults to the clip's title +
    hashtags (at most 2200 characters, 30 hashtags and 20 @ tags);
    share_to_feed also shows the reel in the feed; collaborators are up to
    3 Instagram usernames invited as collaborators; thumb_offset_ms picks
    the cover frame (Instagram takes cover images only from public URLs);
    audio_name names the reel's original audio; ai_generated labels AI
    content; trial_strategy posts a trial reel shown to non-followers only
    (graduated by hand, MANUAL, or when it performs well). Keys of other
    platforms are ignored."""

    caption: str | None = None
    share_to_feed: bool = True
    collaborators: list[str] = Field(
        default_factory=list, max_length=INSTAGRAM_COLLABORATORS_MAX
    )
    thumb_offset_ms: int | None = Field(default=None, ge=0)
    audio_name: str | None = Field(default=None, max_length=200)
    ai_generated: bool = False
    trial_strategy: InstagramTrialStrategy | None = None

    @field_validator("collaborators")
    @classmethod
    def _usernames(cls, names: list[str]) -> list[str]:
        """Collaborators are Instagram usernames (an "@" is dropped)."""
        cleaned = [name.strip().lstrip("@") for name in names]
        for name in cleaned:
            if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", name):
                raise ValueError(f"{name!r} is not an Instagram username")
        return cleaned

    @model_validator(mode="after")
    def _caption_fits(self) -> Self:
        """A caption Instagram would refuse is not accepted."""
        problem = instagram_caption_problem(self.caption or "")
        if problem:
            raise ValueError(problem)
        return self


FACEBOOK_COLLABORATORS_MAX = 10


class FacebookPostOptions(BaseModel):
    """The payload of a Facebook Page reel (SPEC-v2 3.10, Facebook's Reels
    publishing rules). description (hashtags included) defaults to the
    clip's title + hashtags; title is shown with the reel when given;
    ai_generated labels AI content; collaborator_page_ids are the ids of up
    to 10 other Facebook Pages invited to publish the reel too (Facebook
    allows 10 invitations per Page per 24 h). Reels publish to the Page
    publicly. Keys of other platforms are ignored."""

    title: str | None = None
    description: str | None = None
    ai_generated: bool = False
    collaborator_page_ids: list[str] = Field(
        default_factory=list, max_length=FACEBOOK_COLLABORATORS_MAX
    )

    @field_validator("collaborator_page_ids")
    @classmethod
    def _page_ids(cls, ids: list[str]) -> list[str]:
        """Collaborators are numeric Facebook Page ids."""
        cleaned = [page_id.strip() for page_id in ids]
        for page_id in cleaned:
            if not re.fullmatch(r"\d{5,25}", page_id):
                raise ValueError(f"{page_id!r} is not a Facebook Page id")
        return cleaned


Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
# Monday first, like date.weekday().
WEEKDAYS: tuple[Weekday, ...] = get_args(Weekday)
SCHEDULE_TIMES_MAX = 24


class ScheduleRules(BaseModel):
    """The bulk scheduler's rules (SPEC-v2 3.10): the posting days and the
    times of day of the slots, in the IANA timezone (e.g. "Europe/Zurich").
    Each posting day gets posts_per_day slots, the earliest of times
    (default: all of them); skip_days have no slots; the first posting day
    is start_date (default: today). A time that the clocks skip (spring
    forward) is moved forward by the gap; a time that happens twice (fall
    back) is used once, the first time."""

    model_config = ConfigDict(extra="forbid")

    timezone: str = Field(min_length=1, max_length=64)
    times: list[time] = Field(min_length=1, max_length=SCHEDULE_TIMES_MAX)
    posts_per_day: int | None = Field(default=None, ge=1, le=SCHEDULE_TIMES_MAX)
    skip_days: list[Weekday] = Field(default_factory=list)
    start_date: date | None = None

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, key: str) -> str:
        """The timezone must be in the IANA time zone database."""
        try:
            ZoneInfo(key)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"{key!r} is not a known timezone") from exc
        return key

    @field_validator("times")
    @classmethod
    def _wall_clock_times(cls, times: list[time]) -> list[time]:
        """Times are distinct local wall-clock times, kept in order."""
        if any(at.tzinfo is not None for at in times):
            raise ValueError("times are local times, without a UTC offset")
        if len(set(times)) != len(times):
            raise ValueError("times must not repeat")
        return sorted(times)

    @field_validator("skip_days")
    @classmethod
    def _some_posting_day(cls, days: list[Weekday]) -> list[Weekday]:
        """At least one day of the week must have slots."""
        unique = [day for day in WEEKDAYS if day in days]
        if len(unique) == len(WEEKDAYS):
            raise ValueError("every day of the week is skipped")
        return unique

    @model_validator(mode="after")
    def _enough_times(self) -> Self:
        """posts_per_day cannot ask for more slots than there are times."""
        if self.posts_per_day is not None and self.posts_per_day > len(self.times):
            raise ValueError("posts_per_day is more than the number of times")
        return self

    def daily_times(self) -> list[time]:
        """Return the times of the slots of a posting day, earliest first."""
        return self.times[: self.posts_per_day or len(self.times)]


POST_COLLABORATORS_MAX = 10


class PostText(BaseModel):
    """What one post says on its platform (SPEC-v2 3.10), turned into the
    platform's payload by clipforge.post_payload. A field left None takes
    the clip's own (title, description, hashtags). caption is the post's
    text (YouTube/Facebook: the description; TikTok/Instagram: the caption,
    which also carries the title); link (the full video) and the hashtags
    go after it. privacy is a value of the platform (YouTube public /
    unlisted / private, TikTok's privacy levels; Instagram and Facebook
    publish publicly). collaborators are only for the platforms whose API
    takes them (Instagram usernames, Facebook Page ids). options are the
    platform's other settings (e.g. made_for_kids, allow_comment)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=500)
    caption: str | None = Field(default=None, max_length=10_000)
    hashtags: list[str] | None = Field(default=None, max_length=100)
    link: str | None = Field(default=None, max_length=2000)
    privacy: str | None = Field(default=None, max_length=40)
    collaborators: list[str] = Field(
        default_factory=list, max_length=POST_COLLABORATORS_MAX
    )
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("link")
    @classmethod
    def _web_link(cls, link: str | None) -> str | None:
        """The link is an http(s) URL (blank: none)."""
        if link is None or not link.strip():
            return None
        link = link.strip()
        parts = urlsplit(link)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("the link must be an http:// or https:// URL")
        return link


class PostTarget(BaseModel):
    """An account to post a clip to, with what the post says there."""

    model_config = ConfigDict(extra="forbid")

    account_id: int
    text: PostText = Field(default_factory=PostText)


class PostCreate(BaseModel):
    """The body of POST /clips/{id}/posts: draft posts of the clip to each
    target account, to publish at scheduled_at (None: not scheduled yet)
    with the thumbnail asset, if any."""

    model_config = ConfigDict(extra="forbid")

    targets: list[PostTarget] = Field(min_length=1, max_length=50)
    scheduled_at: datetime | None = None
    thumbnail_asset_id: int | None = None


class PostPatch(BaseModel):
    """The body of PATCH /posts/{id}: a new text, time (reschedule; null:
    unscheduled) or thumbnail of a draft or queued post. Fields left out
    keep their value."""

    model_config = ConfigDict(extra="forbid")

    text: PostText | None = None
    scheduled_at: datetime | None = None
    thumbnail_asset_id: int | None = None


class PostQueue(BaseModel):
    """The body of POST /posts/{id}/queue: publish the post at scheduled_at
    (left out: its own time; null: as soon as possible)."""

    model_config = ConfigDict(extra="forbid")

    scheduled_at: datetime | None = None


class BulkSchedule(BaseModel):
    """The body of POST /posts/bulk-schedule: post every clip to every
    target account, each in the account's next free slot of rules; queue
    publishes them (human only), else they stay drafts with their time."""

    model_config = ConfigDict(extra="forbid")

    clip_ids: list[int] = Field(min_length=1, max_length=200)
    targets: list[PostTarget] = Field(min_length=1, max_length=50)
    rules: ScheduleRules
    queue: bool = False


class CampaignBulkSchedule(BaseModel):
    """The body of POST /campaigns/{id}/bulk-schedule: post every clip of
    the campaign's projects to each of the campaign's own accounts (see
    CampaignAccounts), each in the account's next free slot of rules, saying
    text on every platform (a field left None takes the clip's own).
    queue publishes them (human only), else they stay drafts with their
    time."""

    model_config = ConfigDict(extra="forbid")

    clip_ids: list[int] = Field(min_length=1, max_length=200)
    rules: ScheduleRules
    text: PostText = Field(default_factory=PostText)
    queue: bool = False


class CampaignAccounts(BaseModel):
    """The body of PUT /campaigns/{id}/accounts: the owner's own social
    accounts that the campaign is run on (replaces the accounts before; an
    account of a platform the campaign does not allow is refused)."""

    model_config = ConfigDict(extra="forbid")

    account_ids: list[int] = Field(max_length=50)

    @field_validator("account_ids")
    @classmethod
    def _once(cls, ids: list[int]) -> list[int]:
        return list(dict.fromkeys(ids))


CHANNEL_ID_PATTERN = r"UC[0-9A-Za-z_-]{22}"
# A YouTube handle ("@" and 3 to 30 letters, digits, "_", "-" or ".").
HANDLE_PATTERN = r"@[\w.-]{3,30}"
# A Twitch login (lower case letters, digits and "_").
TWITCH_LOGIN_PATTERN = r"[a-z0-9_]{1,25}"


def _youtube_channel_ref(ref: str) -> str:
    """Return the channel id of a channel id, a youtube.com/channel/<id> link
    or a channel's feed URL (?channel_id=<id>), or the "@handle" of a handle
    or a youtube.com/@handle link (the API resolves a handle to its id)."""
    ref = ref.strip()
    if re.fullmatch(CHANNEL_ID_PATTERN, ref) or re.fullmatch(HANDLE_PATTERN, ref):
        return ref
    parts = urlsplit(ref)
    host = (parts.hostname or "").removeprefix("www.").removeprefix("m.")
    if parts.scheme in ("http", "https") and host == "youtube.com":
        match = re.match(rf"/channel/({CHANNEL_ID_PATTERN})(?:/|$)", parts.path)
        match = match or re.match(rf"/({HANDLE_PATTERN})(?:/|$)", parts.path)
        match = match or re.search(
            rf"(?:^|&)channel_id=({CHANNEL_ID_PATTERN})(?:&|$)", parts.query
        )
        if match is not None:
            return match.group(1)
    raise ValueError(
        "give a YouTube channel id (UC...), an @handle or a youtube.com/channel/"
        "UC... or youtube.com/@handle link"
    )


def _twitch_login(ref: str) -> str:
    """Return the login of a Twitch login or a twitch.tv/<login> link."""
    ref = ref.strip()
    login = ref.lower()
    if not re.fullmatch(TWITCH_LOGIN_PATTERN, login):
        parts = urlsplit(ref)
        host = (parts.hostname or "").removeprefix("www.").removeprefix("m.")
        segment = parts.path.strip("/").split("/")[0].lower()
        if not (parts.scheme in ("http", "https") and host == "twitch.tv"):
            segment = ""
        login = segment
    if not re.fullmatch(TWITCH_LOGIN_PATTERN, login):
        raise ValueError("give a Twitch login or a twitch.tv/<login> link")
    return login


# A YouTube channel id ("UC" and 22 characters), as in the channel's RSS feed.
YouTubeChannelId = Annotated[str, Field(pattern=rf"^{CHANNEL_ID_PATTERN}$")]
# A YouTube channel id, handle or a link that names one; validates to the id
# or the "@handle".
YouTubeChannelRef = Annotated[str, AfterValidator(_youtube_channel_ref)]
TwitchLogin = Annotated[str, Field(pattern=rf"^{TWITCH_LOGIN_PATTERN}$")]
# A Twitch login or a twitch.tv link; validates to the login.
TwitchLoginRef = Annotated[str, AfterValidator(_twitch_login)]
# The WebSub (YouTube) or EventSub (Twitch) subscription of a watched source:
# off (no public callback URL), pending (asked, not verified yet),
# subscribed, denied (by the hub), failed (the request failed) or revoked
# (by Twitch). Only "subscribed" sources are pushed; the others are polled.
PushState = Literal["off", "pending", "subscribed", "denied", "failed", "revoked"]
WatchPlatform = Literal["youtube", "twitch"]
WatchEventKind = Literal["upload", "live"]
DetectedVia = Literal["push", "poll"]


class WatchedChannel(BaseModel):
    """A YouTube channel that Auto Import watches (SPEC-v2 3.1): its new
    videos become projects with these settings, source rights and credit
    line. auto_schedule_drafts asks for the clips to be scheduled as drafts
    (the scheduler task wires it). last_checked_at is the time of the last
    feed read that worked (None: never, so the videos already in the feed
    are not imported); last_error is the error of the latest read that
    failed, None once a read works again."""

    id: int
    channel_id: YouTubeChannelId
    title: str
    settings: ProcessingSettings
    source_rights: SourceRights | None
    credit_line: str = Field(max_length=CREDIT_LINE_MAX)
    auto_schedule_drafts: bool
    enabled: bool
    last_checked_at: datetime | None
    last_error: str | None
    created_at: datetime
    push_state: PushState
    push_lease_expires_at: datetime | None
    push_requested_at: datetime | None
    push_error: str | None
    # The campaign whose source channels registered this channel (None: the
    # owner added it); its new videos get the campaign's preset.
    campaign_id: int | None = None


class WatchedChannelCreate(BaseModel):
    """What adding a channel to Auto Import takes: the channel (id, @handle
    or link) and the defaults of the projects of its new videos."""

    channel: YouTubeChannelRef
    settings: ProcessingSettings = Field(default_factory=ProcessingSettings)
    source_rights: SourceRights | None = None
    credit_line: str = Field(default="", max_length=CREDIT_LINE_MAX)
    auto_schedule_drafts: bool = False


class WatchedChannelPatch(BaseModel):
    """The body of PATCH /auto-import/channels/{id}: the defaults of the
    channel's new projects and whether it is watched (enabled).

    Only the fields that are sent change (source_rights null: unset); at
    least one must be sent.
    """

    model_config = ConfigDict(extra="forbid")

    settings: ProcessingSettings = Field(default_factory=ProcessingSettings)
    source_rights: SourceRights | None = None
    credit_line: str = Field(default="", max_length=CREDIT_LINE_MAX)
    auto_schedule_drafts: bool = False
    enabled: bool = True

    @model_validator(mode="after")
    def _something_to_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError(
                "send settings, source_rights, credit_line, "
                "auto_schedule_drafts or enabled"
            )
        return self


class WatchedVideo(BaseModel):
    """A video that Auto Import saw in a watched channel's feed. project_id
    is the project made for it; None for the videos that were already in the
    feed when the channel was added."""

    watched_channel_id: int
    video_id: str = Field(min_length=1)
    title: str
    published_at: datetime | None
    project_id: int | None
    seen_at: datetime


class WatchedStreamer(BaseModel):
    """A Twitch streamer whose go-live the watch reports (T28c). user_id is
    the broadcaster id (None until resolved); push_state is its EventSub
    stream.online subscription (subscription_id at Twitch), else it is
    polled. live_since is set while a poll sees the stream live;
    last_live_at is when the latest live stream started."""

    id: int
    login: TwitchLogin
    user_id: str | None
    display_name: str
    enabled: bool
    push_state: PushState
    push_requested_at: datetime | None
    push_error: str | None
    subscription_id: str | None
    live_since: datetime | None
    last_live_at: datetime | None
    last_checked_at: datetime | None
    last_error: str | None
    created_at: datetime


class WatchedStreamerCreate(BaseModel):
    """What watching a Twitch streamer takes: a login or twitch.tv link."""

    login: TwitchLoginRef


class WatchedStreamerPatch(BaseModel):
    """The body of PATCH /watch/streamers/{id}: whether it is watched."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool


class WatchEvent(BaseModel):
    """An alert of the watch: a new upload (kind "upload", project_id is its
    project) or a stream that went live (kind "live"). published_at is when
    the source says it was published (or went live), detected_at when
    ClipForge saw it, via how (push or poll). external_id is the video or
    stream id."""

    id: int
    platform: WatchPlatform
    kind: WatchEventKind
    external_id: str = Field(min_length=1)
    source_name: str
    title: str
    url: str
    project_id: int | None
    published_at: datetime | None
    detected_at: datetime
    via: DetectedVia


class WatchStatus(BaseModel):
    """The watch's setup (GET /watch/status). push_available: a public
    callback URL is set, so YouTube and Twitch can push (else everything is
    polled); poll_interval_s: the polling interval; twitch_configured: the
    Twitch app keys are set (go-live needs them); handles_supported: the
    YouTube API key is set, so a channel can be added by @handle."""

    push_available: bool
    poll_interval_s: float
    twitch_configured: bool
    handles_supported: bool


class FaceBox(BaseModel):
    """A face (or, where no face was seen, a person; in a shot without
    either, the moving object of pipeline/object_tracking) that reframe
    detected; x, y, width and height are pixels of the source frame, (x, y) the
    top-left corner. mouth is how open the face's mouth is (lip gap over
    face height; None if not measured); track identifies the same face
    across the samples of a shot (pipeline/identity; None if not tracked);
    subject marks the face the fill window follows (pipeline/speaker)."""

    x: float
    y: float
    width: float
    height: float
    score: UnitInterval
    kind: Literal["face", "person", "object"] = "face"
    mouth: float | None = Field(default=None, ge=0)
    track: int | None = Field(default=None, ge=0)
    subject: bool = False


class CropKeyframe(BaseModel):
    """The crop window's left edge x at t seconds into the source, and the
    faces seen then, largest first; y, if set, is the window's top then
    (else the plan's y)."""

    t: float
    x: int = Field(ge=0)
    faces: list[FaceBox]
    y: int | None = Field(default=None, ge=0)


class CropWindow(BaseModel):
    """A window of width x height source pixels at top y whose left edge is
    xs[k] at keyframe k of its crop plan."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    y: int = Field(ge=0)
    xs: list[Annotated[int, Field(ge=0)]]


class CropPlan(BaseModel):
    """How to frame a clip for its aspect: crop_<clip_id>.json (SPEC 6.8).

    The fill window of width x height source pixels at top y follows the
    subject with one keyframe per frame sampled from start to end (5 a
    second). split holds the top and bottom windows of the split layout,
    which follow the left and the right speaker; grid the three windows of
    the grid layout, which follow the left, middle and right speaker (empty
    in a plan made before the grid layout: pipeline/layout_windows adds
    them); inset the window of the pip layout's inset, which follows the
    largest face that is not the subject (None: the inset shows the whole
    frame). facecam is the box around the subject's face that the
    screenshare and gameplay layouts show (None: no face was found, or the
    plan was made before these layouts). layout is the one reframe chose
    for the clip. background is the fit layout's (reframe writes the
    default; pipeline/framing sets the clip's before a render).
    """

    clip_id: int
    start: float
    end: float
    aspect: Aspect
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    y: int = Field(ge=0)
    keyframes: list[CropKeyframe]
    layout: Layout
    split: tuple[CropWindow, CropWindow]
    grid: list[CropWindow] = Field(default_factory=list)
    inset: CropWindow | None = None
    facecam: FrameBox | None = None
    background: FitBackground = "blur"
    preset: ReframePreset | None = None
    # The camera motion of the windows; None (a plan made before the
    # setting): the preset's (pipeline/reframe_presets).
    camera_motion: CameraMotion | None = None


class ReframePresetInfo(BaseModel):
    """A genre reframing preset (GET /reframe-presets), the layout and the
    tracking parameters reframe uses for it (pipeline/reframe_presets).

    layout: the layout of every clip (None: split when two faces persist,
    else fill). split_share: the share of a clip's samples that need two
    faces for split. camera_motion: the camera motion that picking the
    preset sets (pipeline/camera_motion). objects: follow a moving object
    in shots without a face.
    """

    name: ReframePreset
    label: str
    description: str
    layout: Layout | None
    split_share: UnitInterval
    camera_motion: CameraMotion
    objects: bool


class CropTrack(BaseModel):
    """The fill window that reframe planned for a clip in aspect, as the
    editor's crop tool draws it (GET /clips/{id}/crop): a width x height
    window at top y of the frame_width x frame_height source, whose left
    edge is xs[k] at times[k] source seconds. facecam is the facecam box
    that reframe found for the screenshare and gameplay layouts (None: the
    clip shows no face)."""

    aspect: Aspect
    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    y: int = Field(ge=0)
    times: list[float]
    xs: list[int]
    facecam: FrameBox | None = None


API_KEY_NAME_MAX = 100


class ApiKey(BaseModel):
    """An API key of the public REST API /api/v1 (SPEC-v2 3.14, 4). The key
    itself is shown once, when it is made (ApiKeyCreated); only its hash is
    stored. prefix is its first characters, to tell keys apart;
    last_used_at is when a request last came with it (None: never)."""

    id: int
    name: str = Field(min_length=1, max_length=API_KEY_NAME_MAX)
    prefix: str
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreate(BaseModel):
    """Body of POST /api-keys: the name the owner gives the new key."""

    name: str = Field(min_length=1, max_length=API_KEY_NAME_MAX)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, name: str) -> str:
        stripped = name.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


class ApiKeyCreated(ApiKey):
    """A key just made: key is the secret itself, shown this once."""

    key: str


class AgentSetup(BaseModel):
    """What an AI agent needs to reach this ClipForge (Settings -> AI agents &
    API): api_url is this app's address (CLIPFORGE_URL of the MCP server),
    project_dir the checkout with the clipforge-mcp command, mcp_command +
    mcp_args start that MCP server, docs_url is the REST API's Swagger UI."""

    api_url: str
    project_dir: str
    mcp_command: str
    mcp_args: list[str]
    docs_url: str


# The events that webhooks can subscribe to (SPEC-v2 3.14).
WebhookEvent = Literal[
    "project.completed", "clip.rendered", "post.published", "post.failed"
]
WEBHOOK_EVENTS: tuple[WebhookEvent, ...] = get_args(WebhookEvent)
# pending: to be sent (again); delivered: answered 2xx; failed: gave up.
DeliveryStatus = Literal["pending", "delivered", "failed"]
WEBHOOK_URL_MAX = 2000


def _distinct_events(events: list[WebhookEvent]) -> list[WebhookEvent]:
    """Return events without repeats, in the order of WEBHOOK_EVENTS."""
    return [event for event in WEBHOOK_EVENTS if event in events]


WebhookUrl = Annotated[HttpUrl, Field(max_length=WEBHOOK_URL_MAX)]
WebhookEvents = Annotated[
    list[WebhookEvent], Field(min_length=1), AfterValidator(_distinct_events)
]


class Webhook(BaseModel):
    """A webhook (SPEC-v2 3.14, 4): ClipForge POSTs each of its events to
    url, signed with the webhook's secret (HMAC-SHA256). The secret is
    shown once, when the webhook is made (WebhookCreated)."""

    id: int
    url: str
    events: list[WebhookEvent]
    enabled: bool
    created_at: datetime


class WebhookCreate(BaseModel):
    """Body of POST /webhooks."""

    url: WebhookUrl
    events: WebhookEvents


class WebhookUpdate(BaseModel):
    """Body of PATCH /webhooks/{id}: the fields to change."""

    url: WebhookUrl | None = None
    events: WebhookEvents | None = None
    enabled: bool | None = None


class WebhookCreated(Webhook):
    """A webhook just made: secret signs its deliveries; shown this once."""

    secret: str


class WebhookDelivery(BaseModel):
    """One event sent (or to be sent) to one webhook, with its log: the
    attempts, the last answer's HTTP status and the last error. data is the
    event's payload (the "data" of the body that is sent)."""

    id: int
    webhook_id: int
    event: WebhookEvent
    data: dict[str, Any]
    status: DeliveryStatus
    attempts: int
    created_at: datetime
    attempted_at: datetime | None
    next_attempt_at: datetime | None
    response_status: int | None
    error: str | None


class ErrorBody(BaseModel):
    """Every error answer of the API (SPEC 7): a short code (not_found,
    api_key_invalid, rate_limited, ...) and a sentence for the user. Some
    errors add fields (e.g. the failed campaign rules)."""

    model_config = ConfigDict(extra="allow")

    error: str
    message: str


COLLECTION_NAME_MAX = 100
COLLECTION_DESCRIPTION_MAX = 500
# Most clips that one request adds to a collection.
COLLECTION_ADD_MAX = 500


class CollectionClip(BaseModel):
    """What a collection shows of one of its clips: where it comes from, its
    title and status, its overall score and its source span."""

    id: int
    project_id: int
    title: str
    status: ClipStatus
    overall: Score
    start: float
    end: float


class CollectionItem(BaseModel):
    """A clip in a collection (SPEC-v2 4: CollectionItem); position 0 is the
    first of the collection."""

    id: int
    collection_id: int
    clip_id: int
    position: int
    added_at: datetime
    clip: CollectionClip


class Collection(BaseModel):
    """A named, ordered set of clips from any projects (SPEC-v2 3.11, 4:
    Collection); clip_count is how many it holds."""

    id: int
    name: str = Field(min_length=1, max_length=COLLECTION_NAME_MAX)
    description: str = Field(max_length=COLLECTION_DESCRIPTION_MAX)
    created_at: datetime
    updated_at: datetime
    clip_count: int


class CollectionDetail(Collection):
    """A collection with its items, in their order."""

    items: list[CollectionItem]


def _stripped_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValueError("name must not be blank")
    return stripped


class CollectionCreate(BaseModel):
    """Body of POST /collections."""

    name: str = Field(min_length=1, max_length=COLLECTION_NAME_MAX)
    description: str = Field(default="", max_length=COLLECTION_DESCRIPTION_MAX)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, name: str) -> str:
        return _stripped_name(name)


class CollectionUpdate(BaseModel):
    """Body of PATCH /collections/{id}: the fields to change."""

    name: str | None = Field(default=None, min_length=1, max_length=COLLECTION_NAME_MAX)
    description: str | None = Field(default=None, max_length=COLLECTION_DESCRIPTION_MAX)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, name: str | None) -> str | None:
        return None if name is None else _stripped_name(name)


class CollectionAddClips(BaseModel):
    """Body of POST /collections/{id}/items: the clips to add, at the end in
    this order (those already in the collection stay where they are)."""

    clip_ids: list[int] = Field(min_length=1, max_length=COLLECTION_ADD_MAX)


class CollectionManifestClip(BaseModel):
    """One clip of a collection's zip, as manifest.json lists it: file is its
    video's name in the zip."""

    clip_id: int
    project_id: int
    title: str
    hook_text: str
    description: str
    hashtags: list[str]
    overall: Score
    start: float
    end: float
    file: str


class CollectionManifestSkipped(BaseModel):
    """A clip of the collection that the zip leaves out, and why."""

    clip_id: int
    reason: str


class CollectionManifest(BaseModel):
    """The manifest.json of a collection's zip: the clips in it, in the
    collection's order, and those left out."""

    collection_id: int
    name: str
    description: str
    exported_at: datetime
    clips: list[CollectionManifestClip]
    skipped: list[CollectionManifestSkipped]


SEARCH_QUERY_MAX = 200
SEARCH_LIMIT_MAX = 100
MOMENT_LENGTH_MIN = 5.0
MOMENT_LENGTH_MAX = 180.0


class SearchHighlight(BaseModel):
    """Where a search term sits in a hit's text: from the character start up
    to, not including, end."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)


class SearchHit(BaseModel):
    """One transcript segment of a library search (GET /search): where it is
    (project_id, and start, the second of the video where the first matching
    word is said), the whole segment's text with the matches marked, and how
    well it matches (rank: lower is better; BM25)."""

    project_id: int
    project_title: str
    segment_id: int
    start: float
    segment_start: float
    end: float
    text: str
    highlights: list[SearchHighlight]
    rank: float


class ClipFromMoment(BaseModel):
    """Body of POST /search/clips: make a clip of the project's video from
    the moment at seconds (a search hit's start), as long as length seconds
    at most, from the start of the sentence that holds the moment to the end
    of a sentence."""

    project_id: int
    at: float = Field(ge=0)
    length: float = Field(default=30.0, ge=MOMENT_LENGTH_MIN, le=MOMENT_LENGTH_MAX)


class ProjectStorage(BaseModel):
    """The disk space one project uses (GET /storage), in bytes: its uploaded
    source video, the work files of its jobs and its output (rendered clips,
    exports, previews); cleanable is the share of work and preview files
    that "Clean up" deletes."""

    project_id: int
    title: str
    status: JobStatus
    archived_at: datetime | None
    source_bytes: int = Field(ge=0)
    work_bytes: int = Field(ge=0)
    output_bytes: int = Field(ge=0)
    cleanable_bytes: int = Field(ge=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_bytes(self) -> int:
        """Everything the project uses on disk (read-only)."""
        return self.source_bytes + self.work_bytes + self.output_bytes


class StorageReport(BaseModel):
    """GET /storage: every project's disk use, largest first, their sum and
    the free space on the disk of the data directory."""

    projects: list[ProjectStorage]
    total_bytes: int = Field(ge=0)
    free_bytes: int = Field(ge=0)
    data_dir: str


class StorageCleanup(BaseModel):
    """What POST /projects/{id}/cleanup or /archive did: the bytes it freed
    and the project's disk use now."""

    freed_bytes: int = Field(ge=0)
    storage: ProjectStorage


# What an in-app notification is about (SPEC-v2 3.17); "test" is the one the
# owner sends to try the channels; "autopilot_stopped" is a safety stop of a
# campaign's autopilot (SPEC-v2 3.19); "digest" is the daily summary.
NotificationKind = Literal[
    "project_done",
    "render_failed",
    "post_published",
    "post_failed",
    "quota_warning",
    "autopilot_stopped",
    "digest",
    "test",
]
NOTIFICATION_KINDS: tuple[NotificationKind, ...] = get_args(NotificationKind)
NOTIFICATION_TITLE_MAX = 200
NOTIFICATION_BODY_MAX = 1000


class Notification(BaseModel):
    """A message for the owner (SPEC-v2 3.17): what happened (title, body),
    where to see it (link, an app path such as /projects/3) and when;
    read_at is None until the owner reads it."""

    id: int
    kind: NotificationKind
    title: str = Field(min_length=1, max_length=NOTIFICATION_TITLE_MAX)
    body: str = Field(max_length=NOTIFICATION_BODY_MAX)
    link: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationList(BaseModel):
    """GET /notifications: the newest notifications, and how many unread ones
    there are in all."""

    items: list[Notification]
    unread_count: int = Field(ge=0)


class NotificationChannels(BaseModel):
    """GET /notifications/channels: where a notification goes besides the
    app. email is on only if SMTP_HOST is set; email_to is the recipient."""

    email: bool
    email_to: str | None
    desktop: bool


AUTOPILOT_CLIPS_MAX = 10
AUTOPILOT_POSTS_PER_DAY_DEFAULT = 3
# The most that a campaign may be asked to post a day on one account, however
# the owner sets it (SPEC-v2 3.19: a hard cap, not a default).
AUTOPILOT_POSTS_PER_DAY_CAP = 5
AUTOPILOT_DRAFT_TTL_DEFAULT = 3
AUTOPILOT_DRAFT_TTL_MAX = 30


class AutopilotSettingsUpdate(BaseModel):
    """The body of PUT /campaigns/{id}/autopilot (SPEC-v2 3.19): how the
    autopilot of a campaign works. It only ever makes drafts for the owner
    to approve; it never posts, schedules or submits by itself.

    enabled turns it on; max_clips_per_source is how many clips of a new
    source video may become drafts; min_clip_s/max_clip_s (seconds, None:
    the campaign's own range), caption_template (None: the campaign's) and
    brand_template_id (None: the default look) are what its projects are
    made with; slots are the posting slots (None: the posting rules the
    owner gives when approving) and max_posts_per_day is the most posts a
    day on one account (hard cap 5), so a day of slots may not have more
    times; draft_ttl_days is how many days a draft waits before it expires;
    account_ids are the owner's accounts that approved drafts go to."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_clips_per_source: int = Field(default=3, ge=1, le=AUTOPILOT_CLIPS_MAX)
    slots: ScheduleRules | None = None
    max_posts_per_day: int = Field(
        default=AUTOPILOT_POSTS_PER_DAY_DEFAULT, ge=1, le=AUTOPILOT_POSTS_PER_DAY_CAP
    )
    draft_ttl_days: int = Field(
        default=AUTOPILOT_DRAFT_TTL_DEFAULT, ge=1, le=AUTOPILOT_DRAFT_TTL_MAX
    )
    account_ids: list[int] = Field(default_factory=list, max_length=50)
    min_clip_s: float | None = Field(default=None, gt=0, le=3600)
    max_clip_s: float | None = Field(default=None, gt=0, le=3600)
    caption_template: str | None = Field(default=None, min_length=1, max_length=100)
    brand_template_id: int | None = None
    # Whether it also makes a Pro Edit variant of each draft (SPEC-v3 6), in
    # which preset and at most which intensity; only done when the campaign's
    # allow_heavy_edits is "true".
    proedit_enabled: bool = False
    proedit_preset: ProEditPreset = "clean_pro"
    proedit_max_intensity: ProEditIntensity = "standard"

    @field_validator("account_ids")
    @classmethod
    def _once(cls, ids: list[int]) -> list[int]:
        return list(dict.fromkeys(ids))

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        """The length range is in order and a day of slots fits the daily
        limit."""
        if (
            self.min_clip_s is not None
            and self.max_clip_s is not None
            and self.min_clip_s > self.max_clip_s
        ):
            raise ValueError("min_clip_s is over max_clip_s")
        if self.slots is not None and (
            len(self.slots.daily_times()) > self.max_posts_per_day
        ):
            raise ValueError(
                "slots have more times a day than max_posts_per_day: "
                "lower slots.posts_per_day or raise max_posts_per_day"
            )
        return self


class AutopilotSettings(AutopilotSettingsUpdate):
    """The autopilot settings of campaign campaign_id (a campaign that was
    never set up has the defaults: off)."""

    campaign_id: int


DraftStatus = Literal["pending", "needs_fix", "approved", "rejected", "expired"]
# The reasons that the owner may give when rejecting a draft (SPEC-v2 3.19).
RejectReason = Literal[
    "boring", "out_of_context", "bad_crop", "bad_captions", "too_long", "other"
]
FeedbackAction = Literal["approved", "rejected"]
# Who wrote a review note of a draft: the owner in the app, or an agent (API
# key, MCP server).
DraftNoteAuthor = Literal["owner", "agent"]
DRAFT_NOTE_MAX = 2000
DRAFT_NOTES_MAX = 50


class DraftNote(BaseModel):
    """A review note of a draft: text, who wrote it (by) and when (at)."""

    text: str
    by: DraftNoteAuthor
    at: datetime


class Draft(BaseModel):
    """A clip that the autopilot made for the owner to decide on (SPEC-v2
    3.19). A clip that passes the campaign's rules waits as pending in the
    Approval Inbox; one that fails is needs_fix, with the failed rules in
    rule_results. The owner moves it to approved or rejected (decided_at,
    reject_reason), or it expires after the campaign's draft_ttl_days
    (created_at is when it was made). notes are the review notes of the
    owner and of agents, oldest first. Approving and rejecting are the
    owner's alone (human-only, SPEC-v2 3.19)."""

    id: int
    clip_id: int
    campaign_id: int
    status: DraftStatus
    rule_results: list[RuleResult]
    reject_reason: RejectReason | None
    decided_at: datetime | None
    created_at: datetime
    notes: list[DraftNote]


class DraftCreate(BaseModel):
    """The body of POST /drafts: make a draft of clip clip_id (a clip of a
    campaign's project) for the owner's Approval Inbox. It is pending if the
    clip passes the campaign's rules, else needs_fix."""

    model_config = ConfigDict(extra="forbid")

    clip_id: int


class DraftNoteCreate(BaseModel):
    """The body of POST /drafts/{id}/notes: a review note to add."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=DRAFT_NOTE_MAX)

    @field_validator("text")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        """A note has some text besides spaces."""
        if not text.strip():
            raise ValueError("write a note")
        return text.strip()


class DraftApprove(BaseModel):
    """The body of POST /drafts/{id}/approve and of
    POST /campaigns/{id}/drafts/approve (the owner only): the posting rules
    (None: the autopilot's slots; one of them is needed) and what the posts
    say (a field left None takes the clip's own). Each post goes into its
    account's next free slot, at most max_posts_per_day a day."""

    model_config = ConfigDict(extra="forbid")

    rules: ScheduleRules | None = None
    text: PostText = Field(default_factory=PostText)


class DraftReject(BaseModel):
    """The body of POST /drafts/{id}/reject (the owner only): why, if the
    owner says (the reason chips)."""

    model_config = ConfigDict(extra="forbid")

    reason: RejectReason | None = None


class DraftApproval(BaseModel):
    """An approved draft and the queued posts of its clip."""

    draft: Draft
    posts: list[Post]


class FeedbackEvent(BaseModel):
    """What the owner decided about a clip of a campaign (SPEC-v2 3.19):
    approved, or rejected with a reason. It teaches the next curate prompt
    and score of the campaign. clip_id is None once the clip was deleted
    (what was learned stays)."""

    id: int
    clip_id: int | None
    campaign_id: int
    action: FeedbackAction
    reason: RejectReason | None
    at: datetime


# Why a campaign's autopilot makes no drafts although it is on (SPEC-v2 3.19
# safety switches, autopilot.safety).
AutopilotStopReason = Literal[
    "paused",
    "permission_missing",
    "campaign_inactive",
    "campaign_ended",
    "daily_quota",
]
# How many uploads of a campaign in a row may fail before its autopilot is
# turned off (and the owner alerted).
AUTOPILOT_FAILURES_TO_STOP = 3


class AutopilotStop(BaseModel):
    """The autopilot of campaign campaign_id is on but stopped for reason;
    detail says what the owner can do about it."""

    campaign_id: int
    reason: AutopilotStopReason
    detail: str


class AutopilotPauseUpdate(BaseModel):
    """The body of PUT /autopilot/pause: pause (true) or resume (false) the
    autopilot of every campaign."""

    model_config = ConfigDict(extra="forbid")

    paused: bool


class AutopilotStatus(BaseModel):
    """GET /autopilot/status: whether the owner paused every autopilot (since
    paused_at), and the campaigns whose autopilot is on but stopped."""

    paused: bool
    paused_at: datetime | None
    stops: list[AutopilotStop]


# What an edit decision does, by track (SPEC-v3 3.1); the kinds of one track
# may not overlap unless the kind is stackable.
EdlKind = Literal[
    "zoom_punch",
    "zoom_push",
    "zoom_out_reveal",
    "pan",
    "shake",
    "flash",
    "glitch",
    "rgb_split",
    "freeze_frame",
    "speed_ramp",
    "slowmo",
    "transition",
    "grade_change",
    "vignette",
    "grain",
    "overlay",
    "text_pop",
    "emoji_pop",
    "caption_style",
    "sfx",
    "music_bed",
    "silence_before_drop",
    "audio_fx",
]
# Whether the Director (an LLM), the rule-based director, the user in the
# editor or the critic's revision made a plan or an item.
EdlCreatedBy = Literal["director", "rule_director", "user", "critic_revision"]
EdlSource = Literal["auto", "manual"]
ProEditRunStatus = Literal["queued", "running", "done", "failed"]
# What a Pro Edit run does (SPEC-v3 3.8): start makes a new variant's first
# plan, regenerate a new Director plan, critic runs the critic again on the
# current plan, render re-renders it; each ends with the final render.
ProEditRunMode = Literal["start", "regenerate", "critic", "render"]
# The music of a Pro Edit: chosen by the preset, none, or a catalog asset.
PROEDIT_MUSIC_AUTO = "auto"
PROEDIT_MUSIC_NONE = "none"
# The checklist's scale (SPEC-v3 3.7).
CRITIC_SCORE_MAX = 10


class EdlItem(BaseModel):
    """One edit decision of a Pro Edit plan (SPEC-v3 3.1): kind from t_start
    to t_end in seconds of the clip, with its params and the reason that the
    UI shows. id numbers the item within its plan, from 1."""

    id: int = Field(ge=1)
    t_start: float = Field(ge=0)
    t_end: float = Field(gt=0)
    kind: EdlKind
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)
    source: EdlSource = "auto"

    @model_validator(mode="after")
    def _in_order(self) -> Self:
        if self.t_start >= self.t_end:
            raise ValueError("t_start must be before t_end")
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        return self


class ProEditStatus(BaseModel):
    """GET /proedit/status: Pro Edit is available (proedit.enabled); when it
    is off the endpoint answers 404 proedit_disabled instead.
    critic_max_rounds is N of the progress's "critic round n/N" (0: the
    critic is off)."""

    enabled: bool
    critic_max_rounds: int = Field(default=0, ge=0)


class ProEditPlan(BaseModel):
    """The plan of a Pro Edit variant of clip clip_id (SPEC-v3 3.1): version
    counts the plans of the clip from 1 (a new version for each change that
    keeps the one before), items are its edit decisions and rationale is the
    director's summary. style_recipe_id is the StyleRecipe it aims for."""

    id: int
    clip_id: int
    preset: ProEditPreset
    intensity: ProEditIntensity
    style_recipe_id: int | None = None
    version: int = Field(ge=1)
    items: list[EdlItem] = Field(default_factory=list)
    rationale: str = ""
    created_by: EdlCreatedBy

    @model_validator(mode="after")
    def _item_ids_once(self) -> Self:
        ids = [item.id for item in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("item ids must be unique within a plan")
        return self


class CriticScore(BaseModel):
    """What the critic scored one checklist point (SPEC-v3 3.7), 0 to 10,
    and why."""

    check: str = Field(min_length=1)
    score: float = Field(ge=0, le=CRITIC_SCORE_MAX)
    reason: str


# What a critic change does to the plan's items (SPEC-v3 3.7).
CriticChangeOp = Literal["add", "remove", "modify"]


class PlanChange(BaseModel):
    """One difference between a plan and its critic revision ("what
    changed"): item item_id before and after (before None: added; after
    None: removed) and why it changed (the critic's reason, or what
    post-processing did)."""

    op: CriticChangeOp
    item_id: int = Field(ge=1)
    before: EdlItem | None = None
    after: EdlItem | None = None
    reason: str


class IgnoredChange(BaseModel):
    """A change the critic asked for that was not applied: what it asked
    (op on item_id, or the kind it would add), its reason and the problem
    that made the code ignore it."""

    op: CriticChangeOp
    item_id: int | None = None
    kind: EdlKind | None = None
    reason: str
    problem: str


class CriticRound(BaseModel):
    """One critic round (from 1): the scores of plan version plan_version
    and the revision it led to (changes: "what changed"; ignored: the
    critic's changes left out and why; notes: what else stopped or bent
    the revision). A round that passed or stopped the loop changes
    nothing."""

    round: int = Field(ge=1)
    scores: list[CriticScore]
    plan_version: int | None = Field(default=None, ge=1)
    changes: list[PlanChange] = Field(default_factory=list)
    ignored: list[IgnoredChange] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ProEditOptions(BaseModel):
    """What the owner chose for a Pro Edit (SPEC-v3 3.8): the preset and
    intensity, the style recipe to aim for, the music ("auto": the preset's
    pick of the bundled loops; "none"; or a catalog music asset: a library
    asset id or a bundled loop's name), whether the critic runs and whether
    the edit ends on a loop-friendly ending (its last frames and sound blend
    into its opening; a style recipe whose references loop asks for it
    too). The subject cut-out (proedit/segment.py; skipped, with the reason
    logged, when its engine is not installed) puts the subject in front of
    overlays and captions (subject_front) and blurs the background or swaps
    it for background_color (background)."""

    model_config = ConfigDict(extra="forbid")

    preset: ProEditPreset = "clean_pro"
    intensity: ProEditIntensity = "standard"
    style_recipe_id: int | None = None
    music: str = Field(default=PROEDIT_MUSIC_AUTO, min_length=1, max_length=200)
    use_critic: bool = True
    loop_ending: bool = False
    subject_front: bool = False
    background: ProEditBackground = "keep"
    background_color: HexColor = "#101014"


class ProEditRun(BaseModel):
    """One run of Pro Edit on clip clip_id (SPEC-v3 6): the plan it made
    (None until it has one), how many critic rounds ran and their scores,
    the cost in US dollars as estimated before and as spent (None: no LLM
    call), and when it started and finished; error says why a failed run
    failed. job_id is the job that runs it (its progress and ETA), mode what
    it does, options the owner's choices (None for runs made before them)
    and notes the messages the UI shows (why the rule-based Director made
    the plan, why the critic stopped)."""

    id: int
    clip_id: int
    plan_id: int | None = None
    status: ProEditRunStatus = "queued"
    rounds: int = Field(default=0, ge=0)
    critic_scores: list[CriticRound] = Field(default_factory=list)
    cost_estimate: float | None = Field(default=None, ge=0)
    cost_actual: float | None = Field(default=None, ge=0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    job_id: int | None = None
    mode: ProEditRunMode = "start"
    options: ProEditOptions | None = None
    notes: list[str] = Field(default_factory=list)


class ProEditStarted(BaseModel):
    """A Pro Edit run that was queued: the clip it edits (the new variant
    for a start), the run and its job."""

    clip: Clip
    run: ProEditRun
    job_id: int


class ProEditItemsUpdate(BaseModel):
    """PATCH /proedit/clips/{id}/plan: the edit decisions of the new plan
    version (the editor's; each becomes a manual item)."""

    model_config = ConfigDict(extra="forbid")

    items: list[EdlItem] = Field(max_length=500)


class ProEditWord(BaseModel):
    """A word of a clip, from start to end seconds of the rendered clip."""

    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class ProEditTiming(BaseModel):
    """GET /proedit/clips/{id}/timing: what the Pro Edit editor snaps a
    dragged item to (SPEC-v3 3.1): the render's frame rate, the rendered
    clip's length, its words and the beats of its plan's music beds, all in
    seconds of the rendered clip."""

    fps: int = Field(gt=0)
    duration: float = Field(ge=0)
    words: list[ProEditWord] = Field(default_factory=list)
    beats: list[float] = Field(default_factory=list)


class ProEditEstimate(BaseModel):
    """What a Pro Edit is estimated to cost before it runs (SPEC-v3 1.6):
    the LLM tokens and USD (None: no price set) of the Director and of the
    critic at most (every round, every retry), the text the dialog shows,
    the monthly cap and this month's spend (USD), and whether the cap
    already blocks the LLM (the rule-based Director then plans)."""

    director_tokens: int = Field(ge=0)
    director_usd: float | None = Field(ge=0)
    critic_tokens: int = Field(ge=0)
    critic_usd: float | None = Field(ge=0)
    critic_rounds: int = Field(ge=0)
    text: str
    monthly_cap_usd: float | None = None
    month_spend_usd: float = Field(ge=0)
    blocked: bool = False


class StyleRecipe(BaseModel):
    """A look and feel learned from reference links (SPEC-v3 4): features
    are the aggregated numbers (medians and ranges) and description a short
    text about them. It never holds media or media paths."""

    id: int
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    features: dict[str, Any] = Field(default_factory=dict)
    reference_count: int = Field(default=0, ge=0)
    created_at: datetime

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class StyleReference(BaseModel):
    """A reference link of a style recipe: when its media was analyzed and
    when that media was deleted (SPEC-v3 4.2), and when the owner confirmed
    that they may use it (4.1)."""

    id: int
    recipe_id: int
    url: str = Field(min_length=1)
    analyzed_at: datetime | None = None
    deleted_at: datetime | None = None
    rights_confirmed_at: datetime


StyleMetricGroup = Literal[
    "rhythm", "motion", "look", "effects", "captions", "audio", "structure"
]


class StyleMetric(BaseModel):
    """A number of a style recipe (SPEC-v3 4.4): its key, label, unit and
    group, the bounds and step of its slider in the recipe editor, and its
    tolerance: the least width of the range a measured value is scored
    against (proedit/style/recipe.style_match)."""

    key: str
    label: str
    unit: str
    group: StyleMetricGroup
    min: float
    max: float
    step: float = Field(gt=0)
    tolerance: float = Field(gt=0)


class StyleTarget(BaseModel):
    """A metric's target in a style recipe: the median over the references
    that measured it, the range [low, high] across them and how many did
    (0 when it was set by hand or imported)."""

    model_config = ConfigDict(extra="forbid")

    median: float
    low: float
    high: float
    count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if not self.low <= self.median <= self.high:
            raise ValueError("a target needs low <= median <= high")
        return self


class StyleTargets(BaseModel):
    """What a style recipe aims for: a target per metric key (StyleMetric)
    and the caption fill color (the median RGB of the references')."""

    model_config = ConfigDict(extra="forbid")

    metrics: dict[str, StyleTarget] = Field(default_factory=dict)
    caption_color: HexColor | None = None


class StyleMetricMatch(BaseModel):
    """One metric of a style-match: the value measured on the Pro Edit, the
    recipe's target and how well it fits (1 inside the range)."""

    key: str
    label: str
    unit: str
    value: float
    target: StyleTarget
    score: UnitInterval


class StyleMatch(BaseModel):
    """How close a Pro Edit's video is to a style recipe (SPEC-v3 4.4): the
    score 0-100 (None when it measured none of the recipe's metrics) and
    each metric compared, for the video measured at measured_at."""

    clip_id: int
    recipe_id: int
    recipe_name: str
    score: int | None = Field(ge=0, le=100)
    metrics: list[StyleMetricMatch]
    measured_at: datetime


class StyleRecipeExport(BaseModel):
    """A style recipe as an exported JSON file (SPEC-v3 4.5): its name,
    description, the number of references its targets come from and the
    targets. It never holds media, media paths or links; importing it
    makes a new recipe without references."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["clipforge.style_recipe"] = "clipforge.style_recipe"
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    reference_count: int = Field(default=0, ge=0)
    targets: StyleTargets

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value.strip()


class StyleRecipePatch(BaseModel):
    """An edit of a style recipe from its editor: a new name, description
    or targets (the sliders); a field left out keeps its value."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    targets: StyleTargets | None = None


class ProEditPresetInfo(BaseModel):
    """A preset as the Pro Edit dialog shows it (SPEC-v3 3.4): its id,
    display name, one-line description and the moods and BPM range of the
    music it picks."""

    id: ProEditPreset
    name: str
    description: str
    music_moods: list[str]
    bpm_min: int = Field(gt=0)
    bpm_max: int = Field(gt=0)


class ProEditMusicOption(BaseModel):
    """A music bed the owner may pick for a Pro Edit: id is what
    ProEditOptions.music takes (a bundled loop's name or a library asset
    id), with its title, mood tags and whether it is a bundled loop."""

    id: str = Field(min_length=1)
    title: str
    tags: list[str]
    bundled: bool


class ProEditChoices(BaseModel):
    """What the Pro Edit dialog offers for one clip (SPEC-v3 3.8): the
    presets, the music beds and style recipes to pick from, the campaign of
    the clip's project (None: none) with whether its rules allow heavy
    edits, and the highest intensity the slider reaches (the campaign
    autopilot's Pro Edit cap once the owner saved it, else extreme)."""

    presets: list[ProEditPresetInfo]
    music: list[ProEditMusicOption]
    recipes: list[StyleRecipe]
    campaign_id: int | None = None
    campaign_name: str | None = None
    allow_heavy_edits: HeavyEditsAllowed | None = None
    max_intensity: ProEditIntensity = "extreme"
