"""Transcript and subtitle downloads (SPEC-v2 3.4): the text (txt), SubRip
(srt) and WebVTT (vtt) files of a project's source and of a clip.

Both are lists of cues (export.Cue). The source's cues are the segments of
the project's transcript. A clip's cues are the caption lines of its render
(export.caption_cues over polish.rendered_words), in milliseconds from the
clip's start, with its cuts, caption edits and translation applied and its
censored words masked, as its rendered video shows them.
"""

from collections.abc import Sequence
from typing import Literal

from clipforge.captions_templates import get_template
from clipforge.models import Clip, Transcript
from clipforge.pipeline.export import Cue, caption_cues, srt_time
from clipforge.pipeline.polish import rendered_words

TranscriptFormat = Literal["txt", "srt", "vtt"]

MEDIA_TYPES: dict[str, str] = {
    "txt": "text/plain; charset=utf-8",
    "srt": "application/x-subrip; charset=utf-8",
    "vtt": "text/vtt; charset=utf-8",
}

# A WebVTT cue text may not hold these, they start tags and character
# references.
VTT_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}


def vtt_time(time: int) -> str:
    """Return time, in milliseconds, as a WebVTT timestamp: 61415 ->
    00:01:01.415 (a dot before the milliseconds, not SRT's comma)."""
    return srt_time(time).replace(",", ".")


def source_cues(transcript: Transcript) -> list[Cue]:
    """Return a cue for each segment of transcript that has text and shows
    for some time, with its time in milliseconds from the source's start."""
    cues: list[Cue] = []
    for segment in transcript.segments:
        text = " ".join(segment.text.split())
        start, end = round(segment.start * 1000), round(segment.end * 1000)
        if text and end > start:
            cues.append(Cue(start, end, text))
    return cues


def clip_cues(transcript: Transcript, clip: Clip, fps: int) -> list[Cue]:
    """Return the cues of clip's captions as its render at fps frames a
    second shows them.

    Raises StepError if the custom censor list is needed and not valid, and
    ValueError if the clip's caption template does not exist.
    """
    template = get_template(clip.caption_template)
    words = rendered_words(transcript, clip, fps)
    return caption_cues(words, template.max_words_per_line)


def format_cues(cues: Sequence[Cue], fmt: TranscriptFormat) -> str:
    """Return cues as a file of fmt, UTF-8 text with LF line ends.

    txt: one line of text for each cue. srt: numbered cues, each "index",
    "start --> end" (HH:MM:SS,mmm) and its text, then a blank line. vtt: the
    "WEBVTT" header and a blank line, then the cues as in srt but with a dot
    before the milliseconds and without numbers.
    """
    if fmt == "txt":
        return "".join(f"{cue.text}\n" for cue in cues)
    if fmt == "srt":
        return "".join(
            f"{number}\n{srt_time(cue.start)} --> {srt_time(cue.end)}\n{cue.text}\n\n"
            for number, cue in enumerate(cues, 1)
        )
    body = "".join(
        f"{vtt_time(cue.start)} --> {vtt_time(cue.end)}\n{_vtt_text(cue.text)}\n\n"
        for cue in cues
    )
    return f"WEBVTT\n\n{body}"


def _vtt_text(text: str) -> str:
    """Return text with the characters that a WebVTT cue text escapes."""
    return "".join(VTT_ESCAPES.get(char, char) for char in text)
