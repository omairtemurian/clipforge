"""An uploaded SRT or WebVTT file as the transcript (SPEC 6.2 without Whisper).

The settings panel's "Upload SRT or VTT" stores the file as
{data_dir}/subtitles/<token>.srt (save_subtitles; the name is kept for both
formats, the WEBVTT header tells them apart) and the project's
ProcessingSettings.subtitles_id names it. Transcribe then reads its cues
instead of running Whisper: each cue's words share the cue's time in
proportion to their length (cue_words), so every word is flagged
approximate (Word.approximate, Transcript.approximate_times).
"""

import html
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from clipforge.config import Settings
from clipforge.pipeline.transcript_merge import TimedWord

SUBTITLES_DIRNAME = "subtitles"
# The largest subtitle file accepted: 5 MB, hours of speech.
MAX_SUBTITLE_BYTES = 5_000_000
# Words of a cue made of text the subtitles give as a sure thing.
CUE_PROB = 1.0

# SRT "hh:mm:ss,mmm" or WebVTT "[hh:]mm:ss.mmm"; either separator works.
_STAMP = r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[,.](\d{1,3})"
_TIMING = re.compile(rf"^\s*{_STAMP}\s*-->\s*{_STAMP}(?:\s.*)?$")
_TAG = re.compile(r"<[^>]*>|\{[^}]*\}")
_COUNTER = re.compile(r"^\s*\d+\s*$")
_VTT_BLOCKS = ("NOTE", "STYLE", "REGION")


class SubtitlesError(ValueError):
    """An uploaded file that is not usable SRT or WebVTT.

    line is the 1-based line of the file where it went wrong (0 for the
    file as a whole); it also starts the message.
    """

    def __init__(self, message: str, line: int = 0) -> None:
        super().__init__(f"line {line}: {message}" if line else message)
        self.line = line


@dataclass(frozen=True, slots=True)
class Cue:
    """A subtitle shown from start to end seconds with its text on one line."""

    start: float
    end: float
    text: str


def _seconds(hours: str | None, minutes: str, seconds: str, fraction: str) -> float:
    """Return a timestamp's parts as seconds (fraction is the digits after
    the separator: "5" is half a second)."""
    return (
        int(hours or 0) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(fraction) / 10.0 ** len(fraction)
    )


def _is_block_start(line: str) -> bool:
    """Return whether a WebVTT line opens a NOTE, STYLE or REGION block."""
    return any(
        line == name or line.startswith((f"{name} ", f"{name}\t"))
        for name in _VTT_BLOCKS
    )


def parse_subtitles(text: str) -> list[Cue]:
    """Return the cues of SRT or WebVTT text in time order; blank cues are
    dropped.

    A cue is a timing line ("hh:mm:ss,mmm --> hh:mm:ss,mmm"; WebVTT uses "."
    and may leave out the hours and add cue settings after the end) followed
    by its text lines, and an optional counter (SRT) or identifier (WebVTT)
    line before it. Text starting with a WEBVTT line is WebVTT, whose NOTE,
    STYLE and REGION blocks are skipped. Formatting tags such as <i>,
    <00:00:01.000> and {\\an8} are removed. Raises SubtitlesError, with the
    line number, for a timing line that does not parse, a cue that ends
    before it starts, a line that is neither a counter, a timing nor cue text,
    a cue without timing; or for the file as a whole if it has no cue.
    """
    cues: list[Cue] = []
    current: tuple[float, float] | None = None
    lines: list[str] = []
    header: int | None = None
    skipping = False

    source = text.lstrip("\ufeff").splitlines()
    vtt = bool(source) and re.match(r"WEBVTT([ \t]|$)", source[0]) is not None

    def close() -> None:
        words = html.unescape(_TAG.sub("", " ".join(lines))).split()
        if current is not None and words:
            cues.append(Cue(current[0], current[1], " ".join(words)))

    for number, raw in enumerate(source, start=1):
        line = raw.strip()
        if not line:
            if header is not None and current is None and not skipping:
                raise SubtitlesError("the cue has no timing line", header)
            close()
            current, lines, header, skipping = None, [], None, False
        elif skipping:
            continue
        elif "-->" in line:
            timing = _TIMING.match(raw)
            if timing is None:
                raise SubtitlesError(f"cannot read the timing: {line}", number)
            if not vtt and lines and _COUNTER.match(lines[-1]):
                lines.pop()  # the counter of this cue, no blank line before it
            close()
            parts = timing.groups()
            start, end = _seconds(*parts[:4]), _seconds(*parts[4:])
            if end < start:
                raise SubtitlesError(f"the cue ends before it starts: {line}", number)
            current, lines, header = (start, end), [], None
        elif current is not None:
            lines.append(line)
        elif vtt and number == 1:
            skipping = True
        elif vtt and _is_block_start(line):
            skipping = True
        elif header is not None:
            raise SubtitlesError("expected a timing line", number)
        elif vtt or _COUNTER.match(line):
            header = number
        else:
            raise SubtitlesError("expected a cue number or a timing line", number)
    if header is not None and current is None and not skipping:
        raise SubtitlesError("the cue has no timing line", header)
    close()
    if not cues:
        raise SubtitlesError("the file has no subtitle cues")
    return sorted(cues, key=lambda cue: cue.start)


def cue_words(cues: list[Cue], start: float, end: float) -> list[TimedWord]:
    """Return the words of the cues that overlap start..end seconds, in
    source time.

    A cue's words split its time in proportion to their length in
    characters (plus one for the space after each), so each word's time is
    approximate. The last word of each cue ends a segment.
    """
    words: list[TimedWord] = []
    for cue in cues:
        if cue.end <= start or cue.start >= end:
            continue
        texts = cue.text.split()
        weights = [len(word) + 1 for word in texts]
        span, total, at = cue.end - cue.start, sum(weights), cue.start
        for index, (word, weight) in enumerate(zip(texts, weights, strict=True)):
            after = at + span * weight / total
            words.append(
                TimedWord(
                    text=f" {word}",
                    start=round(at, 3),
                    end=round(after, 3),
                    prob=CUE_PROB,
                    segment_end=index == len(texts) - 1,
                    approximate=True,
                )
            )
            at = after
    return words


def subtitles_path(token: str, cfg: Settings) -> Path:
    """Return where the subtitles with token are: {data_dir}/subtitles/<token>.srt."""
    return cfg.data_dir / SUBTITLES_DIRNAME / f"{token}.srt"


def save_subtitles(data: bytes, cfg: Settings) -> str:
    """Check that data is an SRT or WebVTT file (UTF-8, at most
    MAX_SUBTITLE_BYTES, with cues) and save it under a new random token,
    which is returned.

    Raises SubtitlesError if it is not.
    """
    if len(data) > MAX_SUBTITLE_BYTES:
        raise SubtitlesError(f"the file is larger than {MAX_SUBTITLE_BYTES} bytes")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SubtitlesError("the file is not UTF-8 text") from exc
    parse_subtitles(text)
    token = secrets.token_hex(16)
    path = subtitles_path(token, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return token
