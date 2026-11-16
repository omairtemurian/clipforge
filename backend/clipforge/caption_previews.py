"""Preview images of the caption templates (SPEC 7: GET /caption-templates).

Each template gets one PNG: a sample caption drawn by the same ASS builder
and libass filter that render uses, on a dark 9:16 frame. Font sizes meant
for a 1080x1920 render are drawn on a 540x960 frame, so the text is twice
as large as in a render and stays readable in a small tile. PNGs are cached
in {data_dir}/caption_previews as <template>-<hash>.png; the hash covers the
ASS text (so the template, the sample and the emoji map) and the fonts
directory, so editing a template makes a new image and removes the old one.

A live preview (styled_preview) draws a template with a clip's caption
style the same way, for the editor to show while the style is edited; it is
not cached.
"""

import hashlib
import logging
import tempfile
import threading
from pathlib import Path

from clipforge import config
from clipforge.captions_templates import (
    TEMPLATES_DIR,
    CaptionTemplate,
    load_emoji_map,
    load_templates,
)
from clipforge.ffmpeg import run_ffmpeg
from clipforge.fonts import FONTS_DIR
from clipforge.models import CaptionStyle
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.captions import build_ass
from clipforge.pipeline.render_graph import subtitles_filter
from clipforge.pipeline.step import write_text

logger = logging.getLogger(__name__)

_lock = threading.Lock()

PREVIEWS_DIRNAME = "caption_previews"
# Template font sizes are pixels of a 1080x1920 render; drawing them on a
# 540x960 frame makes the sample text twice as large relative to the image.
FRAME = (540, 960)
IMAGE_SIZE = FRAME
BACKGROUND = "#23232b"
HOOK_TEXT = "Watch till the end"
EMPHASIS = ("funny",)
# (text, start ms, end ms): the image shows the frame where "is" is spoken,
# so it has an active word, an emphasis word and an emoji (all on the first
# line); two-line templates also show the second line.
WORDS = (
    ("This", 0, 400),
    ("is", 400, 800),
    ("funny", 800, 1300),
    ("you", 1300, 1600),
    ("will", 1600, 1900),
    ("love", 1900, 2200),
    ("it", 2200, 2600),
)
SHOWN_AT_MS = 500


def previews_dir() -> Path:
    """Return the directory of the cached preview images."""
    return config.settings.data_dir / PREVIEWS_DIRNAME


def preview_ass(template: CaptionTemplate) -> str:
    """Return the ASS file of template's sample caption."""
    words = [CaptionWord(text, start, end) for text, start, end in WORDS]
    return build_ass(
        words,
        template,
        FRAME,
        emphasis_words=EMPHASIS,
        hook_text=HOOK_TEXT,
        emoji_map=load_emoji_map(),
    )


def preview_path(name: str, template: CaptionTemplate) -> Path:
    """Return where the preview image of template `name` is (or will be) cached."""
    digest = hashlib.sha256()
    digest.update(preview_ass(template).encode())
    digest.update(str(FONTS_DIR).encode())
    return previews_dir() / f"{name}-{digest.hexdigest()[:12]}.png"


def ensure_preview(name: str, template: CaptionTemplate) -> Path:
    """Return the preview PNG of template `name`, drawing it unless the
    current one is cached; older images of the template are deleted.

    Raises FFmpegError if ffmpeg fails.
    """
    output = preview_path(name, template)
    with _lock:
        if not output.is_file():
            _draw(name, output, template)
    return output


def _draw(name: str, output: Path, template: CaptionTemplate) -> None:
    """Draw template's preview into output and delete the older images."""
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f".{output.name}")
    try:
        draw_png(preview_ass(template), tmp)
        tmp.replace(output)
    finally:
        tmp.unlink(missing_ok=True)
    for old in output.parent.glob(f"{name}-*.png"):
        if old != output:
            old.unlink(missing_ok=True)
    logger.info("drew the preview of caption template %s: %s", name, output)


def draw_png(ass_text: str, output: Path) -> None:
    """Draw the frame at SHOWN_AT_MS of the ASS file ass_text on the dark
    preview frame into the PNG output (its .ass is written next to it and
    deleted). Raises FFmpegError if ffmpeg fails."""
    ass = output.with_suffix(".ass")
    write_text(ass, ass_text)
    width, height = FRAME
    try:
        run_ffmpeg(
            [
                "-f", "lavfi",
                "-i", f"color=c={BACKGROUND}:s={width}x{height}:r=10:d=1",
                "-vf",
                f"{subtitles_filter(ass)},scale={IMAGE_SIZE[0]}:{IMAGE_SIZE[1]}",
                "-ss", f"{SHOWN_AT_MS / 1000:.3f}", "-frames:v", "1",
                "-f", "image2", output,
            ]
        )  # fmt: skip
    finally:
        ass.unlink(missing_ok=True)


def styled_preview(template: CaptionTemplate, style: CaptionStyle) -> bytes:
    """Return the PNG of template's sample caption with style applied (the
    live preview of a clip's captions). Raises FFmpegError if ffmpeg fails."""
    with tempfile.TemporaryDirectory(prefix="caption-preview-") as tmp:
        output = Path(tmp) / "preview.png"
        draw_png(preview_ass(template.styled(style)), output)
        return output.read_bytes()


def ensure_previews(templates_dir: Path = TEMPLATES_DIR) -> dict[str, Path]:
    """Return the preview PNG of every caption template by name, drawing the
    ones that are not cached."""
    return {
        name: ensure_preview(name, template)
        for name, template in load_templates(templates_dir).items()
    }
