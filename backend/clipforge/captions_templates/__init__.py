"""Caption templates and the keyword -> emoji map (SPEC 6.9).

Each template is a YAML file in this package named after it: karaoke_bold.yaml
holds the template "karaoke_bold". emoji_map.yaml maps lowercase keywords to
the emoji that captions add after them; it is the only source of emoji (no
LLM, no network).
"""

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, RootModel, ValidationError

from clipforge.fonts import FONTS_DIR, available_fonts, bundled_fonts
from clipforge.models import (
    CAPTION_LINES_MAX,
    CAPTION_LINES_MIN,
    CAPTION_WORDS_MAX,
    CAPTION_WORDS_MIN,
    CaptionAnimation,
    CaptionPosition,
    CaptionStyle,
    Clip,
    Emoji,
    HexColor,
)

TEMPLATES_DIR = Path(__file__).resolve().parent
EMOJI_MAP = "emoji_map.yaml"

Keyword = Annotated[str, Field(pattern=r"^[a-z]+$")]


class CaptionTemplate(BaseModel):
    """How a caption template draws captions: the SPEC 6.9 template fields
    and the SPEC-v2 3.4 ones (outline_color, max_lines, animation).

    font names a bundled font as libass selects it (clipforge.fonts). size is
    the font size in pixels of the output frame (libass makes the font's OS/2
    winAscent + winDescent that tall); outline (the stroke) and shadow are
    pixels too. Words show in primary_color, the word being spoken in
    highlight_color and the clip's emphasis words in emphasis_color at 110%
    size; the stroke is outline_color. box puts an opaque box of
    outline_color behind the text (the outline is then its padding). A line
    holds at most max_words_per_line words and max_lines lines show at once;
    animation says how words move (pipeline/caption_effects). emoji adds the
    emoji of emoji_map.yaml after their keywords.
    """

    model_config = ConfigDict(extra="forbid")

    font: str = Field(min_length=1)
    size: int = Field(gt=0)
    primary_color: HexColor
    highlight_color: HexColor
    emphasis_color: HexColor
    outline: float = Field(ge=0)
    shadow: float = Field(ge=0)
    box: bool
    uppercase: bool
    position: CaptionPosition
    max_words_per_line: int = Field(ge=CAPTION_WORDS_MIN, le=CAPTION_WORDS_MAX)
    emoji: bool
    outline_color: HexColor = "#000000"
    max_lines: int = Field(default=1, ge=CAPTION_LINES_MIN, le=CAPTION_LINES_MAX)
    animation: CaptionAnimation = "none"

    def styled(self, style: CaptionStyle) -> "CaptionTemplate":
        """Return this template with the fields that style sets."""
        template_fields = style.model_dump(
            exclude_none=True,
            exclude={"speaker_colors", "word_marks", "translation", "censor"},
        )
        return self.model_copy(update=template_fields)


class EmojiMap(RootModel[dict[Keyword, Emoji]]):
    """Keyword -> emoji: the content of emoji_map.yaml."""


def read_yaml(path: Path) -> object:
    """Return the parsed content of the YAML file in path.

    Raises ValueError if the file is not valid YAML.
    """
    try:
        with path.open(encoding="utf-8") as file:
            return yaml.safe_load(file)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path} is not valid YAML: {exc}") from exc


def load_template(path: Path, fonts_dir: Path = FONTS_DIR) -> CaptionTemplate:
    """Return the template in path.

    Raises ValueError if the file does not hold a valid template or its font
    is not one of the fonts in fonts_dir.
    """
    try:
        template = CaptionTemplate.model_validate(read_yaml(path))
    except ValidationError as exc:
        raise ValueError(f"{path} is not a valid caption template: {exc}") from exc
    if template.font not in bundled_fonts(fonts_dir):
        raise ValueError(f"{path}: font {template.font!r} is not in {fonts_dir}")
    return template


def load_templates(
    templates_dir: Path = TEMPLATES_DIR, fonts_dir: Path = FONTS_DIR
) -> dict[str, CaptionTemplate]:
    """Return every template in templates_dir by name, in name order."""
    return {
        path.stem: load_template(path, fonts_dir)
        for path in sorted(templates_dir.glob("*.yaml"))
        if path.name != EMOJI_MAP
    }


def get_template(name: str) -> CaptionTemplate:
    """Return the template called name; ValueError lists the known names."""
    templates = load_templates()
    if name not in templates:
        known = ", ".join(templates)
        raise ValueError(f"unknown caption template {name!r} (known: {known})")
    return templates[name]


def style_problems(style: CaptionStyle, fonts_dir: Path | None = None) -> list[str]:
    """Return what is wrong with style: a font that is not in fonts_dir (by
    default a bundled or uploaded font)."""
    known = available_fonts() if fonts_dir is None else bundled_fonts(fonts_dir)
    if style.font is None or style.font in known:
        return []
    return [f"caption font {style.font!r} is not a bundled font"]


def clip_template(clip: Clip) -> CaptionTemplate:
    """Return the template of clip with the clip's caption_style applied;
    ValueError lists the known names if the template does not exist."""
    return get_template(clip.caption_template).styled(clip.caption_style)


def load_emoji_map(path: Path = TEMPLATES_DIR / EMOJI_MAP) -> dict[str, str]:
    """Return the keyword -> emoji map in path.

    Raises ValueError if the file does not map lowercase words to emoji: one
    non-ASCII character each, optionally followed by VARIATION SELECTOR-16.
    """
    try:
        return EmojiMap.model_validate(read_yaml(path)).root
    except ValidationError as exc:
        raise ValueError(f"{path} is not a valid emoji map: {exc}") from exc
