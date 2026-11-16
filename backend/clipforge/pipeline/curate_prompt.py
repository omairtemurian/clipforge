"""Text of the curate step's LLM requests (SPEC 6.5).

The system prompt is prompts/curate_base.md, the part every genre shares,
with the rules of the job's genre from prompts/curate_<genre>.md, the clip
length range, the user's prompt-to-clip request (prompts/prompt_to_clip.md),
with clip anything how to read the timeline lines (prompts/clip_anything.md),
and the JSON Schema of ClipCandidate filled in. The user message is one
window of enriched.txt, "[mm:ss.s-mm:ss.s] S0: text" lines with signal
markers (SPEC 6.4, clipforge.pipeline.enrich); with clip anything,
timeline lines of what is seen and heard (timeline_lines) go between them.
When a reply is retried, the user message also lists what was wrong with
the previous reply.
"""

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from string import Template

from pydantic import ValidationError

from clipforge.candidate_rules import length_range
from clipforge.config import Settings
from clipforge.models import (
    ClipCandidate,
    ContentGenre,
    FrameCaption,
    LengthPreset,
    ProcessingSettings,
    SignalEvent,
    SignalKind,
)
from clipforge.pipeline.enrich import PromptLine, timestamp
from clipforge.pipeline.motion import MotionSpan

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
BASE_PROMPT = "curate_base.md"
# The section of a prompt-to-clip request (ProcessingSettings.keyword_prompt).
REQUEST_PROMPT = "prompt_to_clip.md"
# The section on the timeline lines of clip anything.
ANYTHING_PROMPT = "clip_anything.md"
# The name in a timeline line of each kind of event it shows.
TIMELINE_NAMES: dict[SignalKind, str] = {
    "laugh": "LAUGH",
    "applause": "APPLAUSE",
    "cheer": "CHEER",
    "music": "MUSIC",
    "scene_cut": "SCENE CUT",
}
# Validation errors listed in a retry message; the rest are only counted.
MAX_ERRORS = 20


def length_rule(
    presets: Sequence[LengthPreset],
    cfg: Settings,
    custom: tuple[float, float] | None = None,
) -> str:
    """Describe the clip lengths that presets allow, joined with "or":
    "under 30 seconds or 60 to 90 seconds". "auto" also gives the usual
    range: "20 to 180 seconds (most often 20 to 75 seconds)"."""
    rules = []
    for preset in presets:
        min_s, max_s = length_range(preset, cfg, custom)
        if preset == "lt30":
            rules.append(f"under {max_s:g} seconds")
        elif preset == "auto":
            usual = f"{cfg.clip_min_s:g} to {cfg.clip_max_s:g} seconds"
            rules.append(f"{min_s:g} to {max_s:g} seconds (most often {usual})")
        else:
            rules.append(f"{min_s:g} to {max_s:g} seconds")
    return " or ".join(rules)


def request_section(keyword_prompt: str | None) -> str:
    """Return the prompt-to-clip section for the user's natural-language
    request (prompts/prompt_to_clip.md, SPEC-v2 3.2), or "" if it is unset.

    The request's whitespace is collapsed to single spaces and a "$" in it
    is kept as it is.
    """
    request = " ".join((keyword_prompt or "").split())
    if not request:
        return ""
    return fill(PROMPTS_DIR / REQUEST_PROMPT, {"request": request}).strip()


def anything_section(processing: ProcessingSettings) -> str:
    """Return the clip-anything section (prompts/clip_anything.md) when the
    job's AI clipping has clip_anything on, else ""."""
    if processing.clipping != "ai" or not processing.clip_anything:
        return ""
    return (PROMPTS_DIR / ANYTHING_PROMPT).read_text(encoding="utf-8").strip()


def timeline_lines(
    events: Sequence[SignalEvent],
    spans: Sequence[MotionSpan],
    captions: Sequence[FrameCaption],
    end: float,
) -> list[PromptLine]:
    """Return the clip-anything lines of the user message, by start:

        [mm:ss.s-mm:ss.s] CHEER 0.80     an audio event and its intensity
        [mm:ss.s] SCENE CUT              a cut
        [mm:ss.s-mm:ss.s] MOTION 0.75    a span of high motion and its level
        [mm:ss.s] FRAME: caption         what the vision model saw

    Events of a kind without a TIMELINE_NAMES entry (silence, energy peak)
    are left out; a motion span is cut off at end seconds. A caption's
    whitespace is collapsed to single spaces.
    """
    lines: list[tuple[float, int, str]] = []
    for event in events:
        name = TIMELINE_NAMES.get(event.kind)
        if name == "SCENE CUT":
            lines.append((event.start, 0, f"[{timestamp(event.start)}] {name}"))
        elif name is not None:
            span = f"{timestamp(event.start)}-{timestamp(event.end)}"
            lines.append((event.start, 1, f"[{span}] {name} {event.intensity:.2f}"))
    for motion in spans:
        span = f"{timestamp(motion.start)}-{timestamp(min(motion.end, end))}"
        lines.append((motion.start, 2, f"[{span}] MOTION {motion.level:.2f}"))
    for caption in captions:
        text = " ".join(caption.caption.split())
        lines.append((caption.time, 3, f"[{timestamp(caption.time)}] FRAME: {text}"))
    lines.sort(key=lambda line: line[:2])
    return [PromptLine(start, text) for start, _, text in lines]


def genre_prompt(genre: ContentGenre) -> Path:
    """Return the file with the prompt rules of a genre: curate_<genre>.md."""
    return PROMPTS_DIR / f"curate_{genre}.md"


def fill(path: Path, fields: Mapping[str, str]) -> str:
    """Return the prompt template in path with its $placeholders filled in.

    Raises KeyError for a placeholder that fields lacks, and ValueError for a
    "$" that starts no placeholder (write "$$" for a dollar sign).
    """
    return Template(path.read_text(encoding="utf-8")).substitute(fields)


def system_prompt(
    genre: ContentGenre, processing: ProcessingSettings, cfg: Settings
) -> str:
    """Return the curate system prompt for a genre and processing settings.

    It holds the genre's rules for good clips (genre_prompt), the clip length
    ranges of processing.length_presets, the prompt-to-clip request if
    processing.keyword_prompt is set (request_section), how to read the
    timeline lines if clip anything is on (anything_section), and the JSON Schema
    of ClipCandidate, and asks for a {"clips": [...]} object only (SPEC 6.5).
    The genre's file may use the same placeholders as curate_base.md, except
    $genre_rules.
    """
    fields = {
        "length_rule": length_rule(
            processing.length_presets, cfg, processing.custom_length
        ),
        "request_section": request_section(processing.keyword_prompt),
        "anything_section": anything_section(processing),
        "schema": json.dumps(ClipCandidate.model_json_schema(), indent=2),
    }
    rules = fill(genre_prompt(genre), fields).strip()
    text = fill(PROMPTS_DIR / BASE_PROMPT, {**fields, "genre_rules": rules})
    # An empty section leaves blank lines behind.
    return re.sub(r"\n{3,}", "\n\n", text)


def describe_errors(exc: ValidationError) -> str:
    """List a reply's validation errors as "- location: message" lines.

    The location is the path of the bad value, such as clips.0.title, or
    "reply" for the reply as a whole. The bad values are not repeated.
    """
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    lines = []
    for error in errors[:MAX_ERRORS]:
        where = ".".join(str(part) for part in error["loc"]) or "reply"
        lines.append(f"- {where}: {error['msg']}")
    if len(errors) > MAX_ERRORS:
        lines.append(f"- ... and {len(errors) - MAX_ERRORS} more errors")
    return "\n".join(lines)


def user_prompt(lines: Sequence[PromptLine], errors: str | None = None) -> str:
    """Return the user message for a window: its transcript lines.

    errors, given when the previous reply for the window was not valid, is
    added after the lines with a request to reply again.
    """
    text = "\n".join(line.text for line in lines)
    if errors is None:
        return text
    return (
        f"{text}\n\n"
        "Your previous reply for this transcript was not valid:\n"
        f"{errors}\n\n"
        'Reply again with only the JSON object {"clips": [...]} described in '
        "the instructions."
    )
