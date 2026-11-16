"""Captions (SPEC 6.9): a clip's captions as an ASS file, captions_<clip_id>.ass.

The file draws in the pixels of the output frame (PlayResX/Y = the frame
size that render passes in, aspect.aspect_size of the aspect; captions does not
import render, which calls it) with two styles from the caption template:

- Caption: the caption pages (pipeline/caption_lines: up to the template's
  max_lines lines) at the template's position: top, middle, lower third
  (the default: the lines end at 78% of the frame's height, above the
  platforms' buttons and text) or bottom. Each word gets one Dialogue
  event, while it is the active word (caption_lines.active_end), that
  shows its whole page with the word in highlight_color and the template's
  animation (pipeline/caption_effects). Emphasis words show in
  emphasis_color (in highlight_color while active) at EMPHASIS_SCALE
  percent; the words of a speaker that the clip's speaker_colors name show in
  that color. A word that has an emoji mark is followed by that emoji and,
  if the template has emoji on, so is a word whose key is in emoji_map.yaml,
  in clipforge.fonts.EMOJI_FONT (libass has no emoji fallback).
  Word marks (emphasis, emoji) come from the AI (pipeline/caption_emphasis)
  or the editor and are part of the clip's caption_style.
- Hook: the clip's hook_text at the top for the first HOOK_END_MS, on a
  layer above the captions, so libass never moves one to make room for the
  other.

A clip with a caption translation (pipeline/caption_translate) shows the
translated words instead (polish.rendered_words). Text in a script that the
template's font lacks (Persian, Arabic, Hebrew) is drawn in a bundled font
of that script, and right-to-left text gets an auto base direction (style).

Times count from the clip's start, with its cut_ranges taken out (polish):
rendering seeks its input there and leaves the cuts out. ASS colors are
&HAABBGGRR in styles and &HBBGGRR& in override tags; the stroke is the
template's outline_color, and a box template uses BorderStyle 3, whose box
is OutlineColour. libass reads "YCbCr Matrix:
None" as "use the video's own color space" (ffmpeg's subtitles filter
otherwise draws the colors as BT.601).

Captions are written per clip, like crop plans, so they are not one of the
steps in STEP_NAMES; rendering burns them in (SPEC 6.11).
"""

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

from clipforge.captions_templates import (
    CaptionTemplate,
    clip_template,
    load_emoji_map,
)
from clipforge.fonts import covering_font
from clipforge.models import CaptionPosition, Clip, Transcript
from clipforge.pipeline.caption_effects import (
    WordWriter,
    bgr,
    encoding,
    escape,
    page_text,
    word_text,
)
from clipforge.pipeline.caption_lines import (
    CaptionWord,
    active_end,
    color_speakers,
    group_lines,
    group_pages,
    mark_emphasis,
)
from clipforge.pipeline.headline import has_headline
from clipforge.pipeline.polish import rendered_words
from clipforge.pipeline.step import TRANSCRIPT, load_json, write_text

logger = logging.getLogger(__name__)

# The hook shows from the clip's start until this many milliseconds.
HOOK_END_MS = 2500
# The hook's font size as a share of the template's size.
HOOK_SIZE = 0.7
# Shares of the frame: left and right margins of its width; the hook's top
# margin of its height.
MARGIN_X = 0.05
HOOK_MARGIN_Y = 0.1
# Caption position -> (ASS alignment: numpad position, 2 bottom, 5 middle,
# 8 top center; vertical margin as a share of the frame's height). libass
# ignores the vertical margin of middle captions. Top captions start below
# the hook, which is at most a few short lines.
CAPTION_PLACES: dict[CaptionPosition, tuple[int, float]] = {
    "top": (8, 0.18),
    "middle": (5, 0.15),
    "lower_third": (2, 0.22),
    "bottom": (2, 0.15),
}
HOOK_ALIGNMENT = 8
# Half-transparent black shadow.
SHADOW_COLOR = "&H80000000"
STYLE_FORMAT = (
    "Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
    "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, "
    "Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, "
    "MarginV, Encoding"
)
EVENT_FORMAT = "Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"


def captions_path(job_dir: Path, clip_id: int) -> Path:
    """Return the path of a clip's captions: job_dir/captions_<clip_id>.ass."""
    return job_dir / f"captions_{clip_id}.ass"


def centis(ms: int) -> int:
    """Return ms in whole centiseconds, rounded half up: 1415 -> 142."""
    return (ms + 5) // 10


def ass_time(ms: int) -> str:
    """Return ms as an ASS time, H:MM:SS.cc (centis): 2500 -> "0:00:02.50",
    61415 -> "0:01:01.42"."""
    cs = centis(ms)
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def style(
    name: str,
    template: CaptionTemplate,
    font_size: int,
    alignment: int,
    margins: tuple[int, int],
    text: str = "",
) -> str:
    """Return the ASS Style line called name for text, the text its events
    show: template's font (or a bundled font of text's script that the
    template's font lacks: fonts.covering_font) at font_size pixels with its
    colors, outline (in outline_color), shadow and box, at alignment, with
    the margins (left and right, vertical) in pixels, and the Encoding of
    text's direction (caption_effects.encoding).

    Bold, Italic, Underline and StrikeOut are off (the fonts are bold faces,
    fonts.py; libass would embolden them again), ScaleX/Y 100, Spacing and
    Angle 0. SecondaryColour, which only karaoke tags use, is the
    highlight color.
    """
    margin_x, margin_y = margins
    font = covering_font(template.font, text)
    return (
        f"Style: {name},{font},{font_size},"
        f"&H00{bgr(template.primary_color)},&H00{bgr(template.highlight_color)},"
        f"&H00{bgr(template.outline_color)},{SHADOW_COLOR},0,0,0,0,100,100,0,0,"
        f"{3 if template.box else 1},{template.outline:g},{template.shadow:g},"
        f"{alignment},{margin_x},{margin_x},{margin_y},{encoding(text)}"
    )


def dialogue(layer: int, start: int, end: int, style_name: str, text: str) -> str:
    """Return an ASS Dialogue line from start to end ms with no margins."""
    return (
        f"Dialogue: {layer},{ass_time(start)},{ass_time(end)},{style_name},"
        f",0,0,0,,{text}"
    )


def caption_events(
    lines: Sequence[Sequence[CaptionWord]],
    template: CaptionTemplate,
    emoji_map: Mapping[str, str],
    *,
    word_writer: WordWriter = word_text,
) -> list[str]:
    """Return the Caption Dialogue lines of lines, in pages of the template's
    max_lines: for each word, its page with it active, from its start until
    active_end; word_writer draws each word (caption_effects.page_text).

    A word that would be active for less than a centisecond gets none.
    """
    words = [word for line in lines for word in line]
    events: list[str] = []
    position = 0
    for page in group_pages([list(line) for line in lines], template.max_lines):
        first = True
        for active, word in enumerate(word for line in page for word in line):
            position += 1
            following = words[position] if position < len(words) else None
            end = active_end(word, following)
            if centis(end) <= centis(word.start):
                continue
            text = page_text(
                page, active, template, emoji_map, first=first, word_writer=word_writer
            )
            events.append(dialogue(0, word.start, end, "Caption", text))
            first = False
    return events


def build_ass(
    words: Sequence[CaptionWord],
    template: CaptionTemplate,
    frame: tuple[int, int],
    *,
    emphasis_words: Sequence[str] = (),
    speaker_colors: Mapping[str, str] | None = None,
    hook_text: str = "",
    emoji_map: Mapping[str, str],
    word_writer: WordWriter = word_text,
) -> str:
    """Return the ASS file of captions that show words with template, on a
    frame of (width, height) pixels.

    emphasis_words are marked (caption_lines.mark_emphasis, which keeps the
    emphasis that a word's mark pinned), speaker_colors give the words of each
    speaker their color (caption_lines.color_speakers) and the words are
    grouped into lines of the template's max_words_per_line. A hook_text
    that is not blank gets the Hook event, in the template's case.
    word_writer draws each caption word (Pro Edit's kinetic captions pass
    their own); the default is the template's animation.
    """
    width, height = frame
    margin_x = round(width * MARGIN_X)
    alignment, margin_y = CAPTION_PLACES[template.position]
    caption_style = style(
        "Caption",
        template,
        template.size,
        alignment,
        (margin_x, round(height * margin_y)),
        " ".join(word.text for word in words),
    )
    hook_style = style(
        "Hook",
        template,
        round(template.size * HOOK_SIZE),
        HOOK_ALIGNMENT,
        (margin_x, round(height * HOOK_MARGIN_Y)),
        hook_text,
    )
    hook = escape(hook_text.upper() if template.uppercase else hook_text)
    events = [dialogue(1, 0, HOOK_END_MS, "Hook", hook)] if hook else []
    colored = color_speakers(words, speaker_colors or {})
    lines = group_lines(
        mark_emphasis(colored, emphasis_words), template.max_words_per_line
    )
    events += caption_events(lines, template, emoji_map, word_writer=word_writer)
    return "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            f"PlayResX: {width}",
            f"PlayResY: {height}",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: None",
            "",
            "[V4+ Styles]",
            f"Format: {STYLE_FORMAT}",
            caption_style,
            hook_style,
            "",
            "[Events]",
            f"Format: {EVENT_FORMAT}",
            *events,
            "",
        ]
    )


def _draws_hook_text(clip: Clip) -> bool:
    """Return whether the captions draw clip's hook_text: not while it has a
    viral hook or a headline item, which draw their own text."""
    return clip.hook is None and not has_headline(clip.tracks)


def write_captions(
    job_dir: Path,
    clip: Clip,
    frame: tuple[int, int],
    fps: int,
    output: Path | None = None,
) -> Path:
    """Write the captions of clip for a render on a frame of (width, height)
    pixels at fps frames a second into output, by default captions_path in
    job_dir, and return their path.

    The words come from the job's transcript.json (caption_lines.clip_words
    with the clip's caption_overrides), at their times once the clip's
    cut_ranges are cut as the render cuts them (polish.rendered_words), or
    none if the clip's show_captions is off (its hook still shows); the
    clip gives the caption template (with its caption_style), emphasis words,
    the speaker colors and word marks of its caption_style, and hook text
    (none while the clip has a viral hook, which pipeline/hooks draws, or a
    headline item on its text track, pipeline/headline).
    Raises StepError if transcript.json is missing or not valid, and
    ValueError if the template does not exist.
    """
    transcript = load_json(job_dir / TRANSCRIPT, Transcript, "transcribe")
    template = clip_template(clip)
    words = rendered_words(transcript, clip, fps) if clip.show_captions else []
    text = build_ass(
        words,
        template,
        frame,
        emphasis_words=clip.emphasis_words,
        speaker_colors=clip.caption_style.speaker_colors,
        hook_text=clip.hook_text if _draws_hook_text(clip) else "",
        emoji_map=load_emoji_map(),
    )
    output = captions_path(job_dir, clip.id) if output is None else output
    write_text(output, text)
    logger.info(
        "wrote captions of clip %d (%d words, template %s) to %s",
        clip.id,
        len(words),
        clip.caption_template,
        output,
    )
    return output
