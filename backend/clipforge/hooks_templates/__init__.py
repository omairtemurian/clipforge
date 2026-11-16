"""Viral hook templates (SPEC-v2 3.5): original looks for the first 2-3 s
of a clip, drawn by pipeline/hooks.

Each template is a YAML file in this package named after it: slam_pop.yaml
holds the template "slam_pop". A template has one to three text layers
(text overlay props, pipeline/text_overlay) whose text holds "{text}" where
the hook's text goes, an optional punch-in zoom and an optional whoosh
from the bundled sound effects (assets/sfx, CC0).
"""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from clipforge.captions_templates import read_yaml
from clipforge.fonts import FONTS_DIR, bundled_fonts
from clipforge.models import (
    HOOK_SECONDS,
    HOOK_SECONDS_MAX,
    HOOK_SECONDS_MIN,
    HookTemplateInfo,
    TextProps,
)

TEMPLATES_DIR = Path(__file__).resolve().parent
SFX_DIR = Path(__file__).resolve().parents[3] / "assets" / "sfx"
# What a layer's text holds where the hook's text goes.
TEXT_SLOT = "{text}"


class HookPunch(BaseModel):
    """A punch-in zoom: the frames grow to scale times their size over
    attack seconds from the clip's start (eased out), hold, and shrink back
    to their size over the last release seconds of the hook."""

    model_config = ConfigDict(extra="forbid")

    scale: float = Field(gt=1, le=1.5)
    attack: float = Field(gt=0, le=2)
    release: float = Field(gt=0, le=1)


class HookTemplate(BaseModel):
    """How a hook template draws a hook: label and description to show;
    duration, its default seconds; text uppercased if uppercase and wrapped
    to lines of at most max_chars_per_line characters (max_lines lines; the
    font shrinks for longer lines); layers drawn in order (later on top),
    each with TEXT_SLOT in its text; punch, its zoom (None: none); sound, a
    file name in SFX_DIR (None: silent) mixed in at sound_volume."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=40)
    description: str = Field(min_length=1, max_length=200)
    duration: float = Field(
        default=HOOK_SECONDS, ge=HOOK_SECONDS_MIN, le=HOOK_SECONDS_MAX
    )
    uppercase: bool = False
    max_chars_per_line: int = Field(ge=6, le=40)
    max_lines: int = Field(default=3, ge=1, le=4)
    layers: list[TextProps] = Field(min_length=1, max_length=3)
    punch: HookPunch | None = None
    sound: str | None = None
    sound_volume: float = Field(default=0.8, gt=0, le=2)

    @model_validator(mode="after")
    def _check_layers(self) -> Self:
        """Reject a template whose layers never show the hook's text."""
        if not any(TEXT_SLOT in layer.text for layer in self.layers):
            raise ValueError(f"no layer's text holds {TEXT_SLOT}")
        return self

    def info(self, name: str) -> HookTemplateInfo:
        """Return this template, called name, as GET /hook-templates lists it."""
        return HookTemplateInfo(
            name=name,
            label=self.label,
            description=self.description,
            duration=self.duration,
            punch=self.punch.scale if self.punch else 1.0,
            sound=self.sound is not None,
        )


def load_template(
    path: Path, fonts_dir: Path = FONTS_DIR, sfx_dir: Path = SFX_DIR
) -> HookTemplate:
    """Return the hook template in path.

    Raises ValueError if the file does not hold a valid template, a layer's
    font is not one of the fonts in fonts_dir or its sound is not a file in
    sfx_dir.
    """
    try:
        template = HookTemplate.model_validate(read_yaml(path))
    except ValidationError as exc:
        raise ValueError(f"{path} is not a valid hook template: {exc}") from exc
    fonts = bundled_fonts(fonts_dir)
    for layer in template.layers:
        if layer.font not in fonts:
            raise ValueError(f"{path}: font {layer.font!r} is not in {fonts_dir}")
    if template.sound is not None and not (sfx_dir / template.sound).is_file():
        raise ValueError(f"{path}: sound {template.sound!r} is not in {sfx_dir}")
    return template


def load_templates(templates_dir: Path = TEMPLATES_DIR) -> dict[str, HookTemplate]:
    """Return every hook template in templates_dir by name, in name order."""
    return {
        path.stem: load_template(path) for path in sorted(templates_dir.glob("*.yaml"))
    }


def get_template(name: str) -> HookTemplate:
    """Return the hook template called name; ValueError lists the known
    names."""
    templates = load_templates()
    if name not in templates:
        raise ValueError(
            f"unknown hook template {name!r} (known: {', '.join(templates)})"
        )
    return templates[name]


def sound_path(template: HookTemplate) -> Path | None:
    """Return the file of template's whoosh; None if it has none."""
    return None if template.sound is None else SFX_DIR / template.sound
