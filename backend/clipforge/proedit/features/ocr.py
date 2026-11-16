"""Reading words from images with Tesseract OCR (SPEC-v3 4.3 captions).

The `tesseract` program (Homebrew `tesseract`, 5.x, with its `eng` data)
reads a list of images in one run: `tesseract <list file> stdout --psm 3
-l eng tsv` (fully automatic page segmentation; one TSV row per page,
block, paragraph, line and word, `page_num` counting the listed images
from 1). Word rows (level 5) with text and a confidence of at least
MIN_CONFIDENCE (0..100) are kept; the line of a word is its (block,
paragraph, line) on its page. Verified with `tesseract --help-extra` and
the TSV of tesseract 5.5.4 (docs/decisions.md, TASK-230).
"""

import logging
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
from pydantic import BaseModel

from clipforge.pipeline.step import StepError

TESSERACT = "tesseract"
LANGUAGE = "eng"
PAGE_SEGMENTATION = "3"
MIN_CONFIDENCE = 60.0
WORD_LEVEL = "5"
COLUMNS = 12
TIMEOUT_S = 600

Grey = npt.NDArray[np.uint8]

logger = logging.getLogger(__name__)


class OcrWord(BaseModel):
    """A word read from an image: its line (block, paragraph, line), box
    in pixels, confidence (0..100) and text."""

    line: tuple[int, int, int]
    left: int
    top: int
    width: int
    height: int
    confidence: float
    text: str


def tesseract_path() -> str | None:
    """Return the path of the tesseract program, or None if it is not
    installed."""
    return shutil.which(TESSERACT)


def read_words(images: Sequence[Grey]) -> list[list[OcrWord]]:
    """Return the words of each image (module doc), in reading order.

    Raises StepError if tesseract is missing or fails.
    """
    program = tesseract_path()
    if program is None:
        raise StepError("tesseract is not installed: run `brew install tesseract`")
    words: list[list[OcrWord]] = [[] for _ in images]
    if not images:
        return words
    with tempfile.TemporaryDirectory(prefix="clipforge-ocr-") as tmp:
        folder = Path(tmp)
        paths = []
        for index, image in enumerate(images):
            path = folder / f"{index:05d}.png"
            if not cv2.imwrite(str(path), image):
                raise StepError(f"cannot write the OCR image {path}")
            paths.append(str(path))
        listing = folder / "images.txt"
        listing.write_text("\n".join(paths) + "\n", encoding="utf-8")
        command = [program, str(listing), "stdout", "--psm", PAGE_SEGMENTATION]
        command += ["-l", LANGUAGE, "tsv"]
        try:
            result = subprocess.run(
                command, capture_output=True, check=False, timeout=TIMEOUT_S
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise StepError(f"tesseract failed: {exc}") from exc
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", "replace").strip()
        raise StepError(f"tesseract failed ({result.returncode}): {error}")
    for page, word in parse_tsv(result.stdout.decode("utf-8", "replace")):
        if 0 <= page < len(words):
            words[page].append(word)
    return words


def parse_tsv(tsv: str) -> list[tuple[int, OcrWord]]:
    """Return the (image index from 0, word) of each kept word row of
    tesseract's TSV output (module doc)."""
    found = []
    for row in tsv.splitlines()[1:]:
        cells = row.split("\t")
        if len(cells) < COLUMNS or cells[0] != WORD_LEVEL:
            continue
        text = "\t".join(cells[COLUMNS - 1 :]).strip()
        try:
            page, block, paragraph, line = (int(cell) for cell in cells[1:5])
            left, top, width, height = (int(cell) for cell in cells[6:10])
            confidence = float(cells[10])
        except ValueError:
            logger.debug("skipping a tesseract row: %r", row)
            continue
        if text and confidence >= MIN_CONFIDENCE:
            word = OcrWord(
                line=(block, paragraph, line),
                left=left,
                top=top,
                width=width,
                height=height,
                confidence=confidence,
                text=text,
            )
            found.append((page - 1, word))
    return found
