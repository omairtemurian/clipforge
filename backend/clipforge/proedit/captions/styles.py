"""The kinetic caption styles of Pro Edit (SPEC-v3 3.3): one YAML file in
styles/ per style, named after the CaptionStyleParams.style it draws.

A file holds the look as a caption template (captions_templates, with its
animation left to the motion here) and how the spoken word moves: motion
"pop" or "bounce" and glow, whether it glows in highlight_color. The
existing caption templates are not touched.
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from clipforge.captions_templates import CaptionTemplate, read_yaml
from clipforge.fonts import FONTS_DIR, bundled_fonts

STYLES_DIR = Path(__file__).resolve().parent / "styles"
Motion = Literal["pop", "bounce"]


class KineticStyle(BaseModel):
    """caption is the template the words are drawn with; the spoken word
    moves as motion says and, if glow, has a halo of highlight_color (its
    fill is then primary_color)."""

    model_config = ConfigDict(extra="forbid")

    motion: Motion
    glow: bool
    caption: CaptionTemplate


def load_style(path: Path, fonts_dir: Path = FONTS_DIR) -> KineticStyle:
    """Return the style in path.

    Raises ValueError if the file does not hold a valid style or its font is
    not one of the fonts in fonts_dir.
    """
    try:
        style = KineticStyle.model_validate(read_yaml(path))
    except ValidationError as exc:
        raise ValueError(f"{path} is not a valid kinetic style: {exc}") from exc
    if style.caption.font not in bundled_fonts(fonts_dir):
        raise ValueError(f"{path}: font {style.caption.font!r} is not in {fonts_dir}")
    return style


def load_styles(
    styles_dir: Path = STYLES_DIR, fonts_dir: Path = FONTS_DIR
) -> dict[str, KineticStyle]:
    """Return every style in styles_dir by name, in name order."""
    return {
        path.stem: load_style(path, fonts_dir)
        for path in sorted(styles_dir.glob("*.yaml"))
    }


def get_style(name: str) -> KineticStyle:
    """Return the style called name; ValueError lists the known names."""
    styles = load_styles()
    if name not in styles:
        raise ValueError(
            f"unknown kinetic caption style {name!r} (known: {', '.join(styles)})"
        )
    return styles[name]
