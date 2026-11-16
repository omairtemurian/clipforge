"""The burned-in captions of a style reference (SPEC-v3 4.3 captions).

OCR_FPS frames a second, at the video's own size, go through the glyph
mask (features/glyphs) and Tesseract (features/ocr), BATCH frames per
tesseract run. A caption line is an OCR line with at least
MIN_LINE_LETTERS letters whose size (below) is at least MIN_CAPTION_SIZE,
so small on-screen text (a watermark, UI) and digit-only text (a counter,
a timecode) are no caption; its words are the words with a letter or
digit. Of each line:

- words: its word count;
- size: the SIZE_PERCENTILE percentile of the heights of its glyph fills
  (the glyphs centered in its words' boxes: about the cap height, as
  lowercase letters without ascenders are the shorter ones) over the frame
  height;
- position: the center of its glyphs' box over the frame width / height
  (0 left / top, 1 right / bottom);
- color: the median RGB of its glyph fill pixels;
- letters and uppercase letters.

The features are medians over every line read (so a caption on screen for
longer weighs more), the share of sampled frames with a line, and the
share of uppercase letters among all letters. Without tesseract installed
there are no caption features (None).
"""

import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from clipforge.ffmpeg import FFmpegError, probe_media
from clipforge.models import UnitInterval
from clipforge.pipeline.frame_stream import stream_frames
from clipforge.pipeline.step import StepError
from clipforge.proedit.features.color import Frame
from clipforge.proedit.features.glyphs import Glyphs, find_glyphs
from clipforge.proedit.features.ocr import OcrWord, read_words, tesseract_path

OCR_FPS = 2
BATCH = 16
MIN_LINE_LETTERS = 2
MIN_CAPTION_SIZE = 0.02
SIZE_PERCENTILE = 80
DECIMALS = 4

logger = logging.getLogger(__name__)


class CaptionFeatures(BaseModel):
    """The captions of a video (module doc): frames sampled, the share with
    a caption line, lines read, median words per line, size (glyph height
    over frame height), position (0..1 of the frame) and fill color
    ("#rrggbb"), and the share of uppercase letters; None without lines."""

    frames: int = Field(ge=0)
    text_share: UnitInterval
    lines: int = Field(ge=0)
    words_per_line: float | None = None
    size_ratio: float | None = None
    position_x: UnitInterval | None = None
    position_y: UnitInterval | None = None
    color: str | None = None
    uppercase_ratio: UnitInterval | None = None


@dataclass(frozen=True)
class CaptionLine:
    """One caption line read on one frame (module doc)."""

    words: int
    letters: int
    uppercase: int
    size: float
    center_x: float
    center_y: float
    color: tuple[float, float, float]


def analyze_captions(path: Path) -> CaptionFeatures | None:
    """Return the caption features of the video at path (module doc), or
    None if tesseract is not installed. Raises StepError if the video cannot
    be read or tesseract fails."""
    if tesseract_path() is None:
        logger.warning("tesseract is not installed: no caption features")
        return None
    try:
        info = probe_media(path)
        count = math.floor(info.duration * OCR_FPS)
        size = (info.width // 2 * 2, info.height // 2 * 2)
        lines: list[list[CaptionLine]] = []
        batch: list[tuple[Frame, Glyphs]] = []
        for rgb in stream_frames(path, 0.0, count, size, OCR_FPS):
            batch.append((rgb, find_glyphs(rgb)))
            if len(batch) == BATCH:
                lines += _read(batch)
                batch = []
        lines += _read(batch)
    except FFmpegError as exc:
        raise StepError(f"cannot read the captions of {path}: {exc}") from exc
    return caption_features(lines)


def caption_features(frames: list[list[CaptionLine]]) -> CaptionFeatures:
    """Return the caption features of the lines read on each sampled frame."""
    lines = [line for frame in frames for line in frame]
    with_text = sum(1 for frame in frames if frame)
    features = CaptionFeatures(
        frames=len(frames),
        text_share=round(with_text / len(frames), DECIMALS) if frames else 0.0,
        lines=len(lines),
    )
    if not lines:
        return features
    letters = sum(line.letters for line in lines)
    color = np.median(np.asarray([line.color for line in lines]), axis=0)
    return features.model_copy(
        update={
            "words_per_line": _median([line.words for line in lines]),
            "size_ratio": _median([line.size for line in lines]),
            "position_x": _median([line.center_x for line in lines]),
            "position_y": _median([line.center_y for line in lines]),
            "color": "#" + "".join(f"{round(float(c)):02x}" for c in color),
            "uppercase_ratio": round(
                sum(line.uppercase for line in lines) / letters, DECIMALS
            )
            if letters
            else None,
        }
    )


def _read(batch: list[tuple[Frame, Glyphs]]) -> list[list[CaptionLine]]:
    """Return the caption lines of each frame of batch; frames without
    glyphs are not sent to tesseract."""
    found: list[list[CaptionLine]] = [[] for _ in batch]
    todo = [k for k, (_, glyphs) in enumerate(batch) if len(glyphs.ids)]
    pages = read_words([batch[k][1].mask for k in todo])
    for k, words in zip(todo, pages, strict=True):
        rgb, glyphs = batch[k]
        found[k] = frame_lines(rgb, glyphs, words)
    return found


def frame_lines(rgb: Frame, glyphs: Glyphs, words: list[OcrWord]) -> list[CaptionLine]:
    """Return the caption lines of a frame from the words OCR read on its
    glyph mask (module doc)."""
    by_line: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        if any(char.isalnum() for char in word.text):
            by_line.setdefault(word.line, []).append(word)
    lines = []
    for line_words in by_line.values():
        text = "".join(word.text for word in line_words)
        inside = sorted(
            {
                k
                for word in line_words
                for k in glyphs.inside(word.left, word.top, word.width, word.height)
            }
        )
        if sum(char.isalpha() for char in text) < MIN_LINE_LETTERS or not inside:
            continue
        line = _line(rgb, glyphs, inside, line_words, text)
        if line.size >= MIN_CAPTION_SIZE:
            lines.append(line)
    return lines


def _line(
    rgb: Frame, glyphs: Glyphs, inside: list[int], words: list[OcrWord], text: str
) -> CaptionLine:
    """Return the caption line made of words whose glyphs are inside."""
    height, width = rgb.shape[:2]
    boxes = glyphs.boxes[inside]
    left, top = int(boxes[:, 0].min()), int(boxes[:, 1].min())
    right = int((boxes[:, 0] + boxes[:, 2]).max())
    bottom = int((boxes[:, 1] + boxes[:, 3]).max())
    region = glyphs.labels[top:bottom, left:right]
    fill = np.isin(region, glyphs.ids[inside])
    pixels = rgb[top:bottom, left:right][fill]
    color = np.median(pixels, axis=0)
    return CaptionLine(
        words=len(words),
        letters=sum(char.isalpha() for char in text),
        uppercase=sum(char.isupper() for char in text),
        size=float(np.percentile(boxes[:, 3], SIZE_PERCENTILE)) / height,
        center_x=(left + right) / 2 / width,
        center_y=(top + bottom) / 2 / height,
        color=(float(color[0]), float(color[1]), float(color[2])),
    )


def _median(values: list[float] | list[int]) -> float:
    """Return the median of values, rounded."""
    return round(float(np.median(values)), DECIMALS)
