"""The six original Pro Edit presets (SPEC-v3 3.4): one YAML file in presets/
per ProEditPreset, loaded into a PresetDef.

A preset declares the kinds of edit decisions it may use, its intensity
budgets (each at most the global one, budgets.effective_budget), its music
(moods and BPM range of the bed), its look (caption style, base grade,
vignette, grain), its overlay set, default params and lengths of its moves
(beat_lengths: in beats over a music bed, so a move on a beat also ends on
one), snap modes, which visual events get a whoosh, and its Director rules: on
which signal moments (Trigger) which moves happen, from which intensity on.
A move is a kind or a composite: "skull_moment" (the Skull Moment sequence,
SkullSpec) or "bass_drop" (an impact and a bass drop, with a silence before
it when there is music).
"""

from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal, Self, cast, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from clipforge.captions_templates import read_yaml
from clipforge.models import EdlItem, EdlKind, ProEditIntensity, ProEditPreset
from clipforge.proedit import edl_params as p
from clipforge.proedit.audio.sfx_place import EventKind
from clipforge.proedit.budgets import INTENSITIES, PresetBudget, effective_budget
from clipforge.proedit.composites import Composite
from clipforge.proedit.edl import EdlValidationError, parse_item
from clipforge.proedit.overlays.procedural import asset_problem
from clipforge.proedit.snap import SnapMode

PRESETS_DIR = Path(__file__).resolve().parent / "presets"
Trigger = Literal[
    "hook",
    "emphasis",
    "punchline",
    "setup",
    "payoff",
    "scene_cut",
    "downbeat",
    "beat",
    "energy_peak",
]
Move = EdlKind | Composite
# The kinds that a preset's look puts over the whole clip.
LOOK_KINDS: frozenset[EdlKind] = frozenset(
    {"caption_style", "grade_change", "vignette", "grain", "music_bed"}
)
SKULL_KINDS: frozenset[EdlKind] = frozenset(
    {"freeze_frame", "grade_change", "overlay", "zoom_punch", "shake", "sfx"}
)
DROP_KINDS: frozenset[EdlKind] = frozenset({"sfx", "audio_fx", "silence_before_drop"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rule(_Strict):
    """On each moment of signal (every every-th, from the phase-th), from
    intensity from_intensity up: every move of moves, or with cycle one
    move per moment in turn. params override the preset's per kind."""

    signal: Trigger
    moves: list[Move] = Field(min_length=1)
    from_intensity: ProEditIntensity = "clean"
    every: int = Field(default=1, ge=1)
    phase: int = Field(default=0, ge=0)
    cycle: bool = False
    params: dict[EdlKind, dict[str, Any]] = Field(default_factory=dict)


class MusicSpec(_Strict):
    """The bed the preset wants: its moods, BPM range and level."""

    moods: list[str] = Field(min_length=1)
    bpm: tuple[Annotated[int, Field(gt=0)], Annotated[int, Field(gt=0)]]
    gain_db: float = Field(default=-18.0, ge=-40, le=0)

    @model_validator(mode="after")
    def _range(self) -> Self:
        if self.bpm[0] > self.bpm[1]:
            raise ValueError("the BPM range must go from low to high")
        return self


class SkullSpec(_Strict):
    """The Skull Moment sequence: hold_s seconds of a frozen frame in look,
    with the overlay on the face, at most max_moments per clip."""

    hold_s: float = Field(default=1.5, ge=1.0, le=2.0)
    look: Literal["bw", "dark"] = "bw"
    overlay: str = "skull"
    max_moments: int = Field(default=1, ge=1)


class PresetDef(_Strict):
    """One preset (module docstring); name is its display name."""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    kinds: frozenset[EdlKind]
    budgets: dict[ProEditIntensity, PresetBudget] = Field(default_factory=dict)
    music: MusicSpec
    caption_style: p.CaptionStyleParams
    grade: p.GradeChangeParams | None = None
    vignette: p.VignetteParams | None = None
    grain: p.GrainParams | None = None
    overlays: list[str] = Field(default_factory=list)
    params: dict[EdlKind, dict[str, Any]] = Field(default_factory=dict)
    lengths: dict[EdlKind, Annotated[float, Field(gt=0, le=10)]] = Field(
        default_factory=dict
    )
    beat_lengths: dict[EdlKind, Annotated[int, Field(ge=1, le=16)]] = Field(
        default_factory=dict
    )
    snap: dict[EdlKind, SnapMode] = Field(default_factory=dict)
    whooshes: frozenset[EventKind] = frozenset(get_args(EventKind))
    rules: list[Rule] = Field(min_length=1)
    interrupts: list[EdlKind] = Field(default_factory=list)
    skull: SkullSpec | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        problems = [*self._kind_problems(), *self._param_problems()]
        problems += [
            f"overlay set: {why}" for a in self.overlays if (why := asset_problem(a))
        ]
        for intensity in INTENSITIES:
            try:
                effective_budget(intensity, self.budgets.get(intensity))
            except ValueError as error:
                problems.append(str(error))
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def _kind_problems(self) -> list[str]:
        optional: list[tuple[EdlKind, object]] = [
            ("grade_change", self.grade),
            ("vignette", self.vignette),
            ("grain", self.grain),
        ]
        look: set[EdlKind] = {"caption_style", "music_bed"}
        look |= {kind for kind, params in optional if params is not None}
        needed: dict[str, frozenset[EdlKind]] = {
            "the look": frozenset(look),
            "interrupts": frozenset(self.interrupts),
        }
        for rule in self.rules:
            for move in rule.moves:
                if move == "skull_moment":
                    needed["skull_moment"] = SKULL_KINDS
                elif move == "bass_drop":
                    needed["bass_drop"] = DROP_KINDS
                else:
                    needed[f"the {rule.signal} rule"] = needed.get(
                        f"the {rule.signal} rule", frozenset()
                    ) | {move}
        problems = [
            f"{what} uses {', '.join(sorted(kinds - self.kinds))}, which the "
            "preset does not allow"
            for what, kinds in needed.items()
            if kinds - self.kinds
        ]
        has_skull = any("skull_moment" in rule.moves for rule in self.rules)
        if has_skull != (self.skull is not None):
            problems.append("skull is set exactly when a rule makes a skull_moment")
        if self.skull is not None and (why := asset_problem(self.skull.overlay)):
            problems.append(f"skull overlay: {why}")
        if "overlay" in self.kinds and not self.overlays and self.skull is None:
            problems.append("the overlay kind needs an overlay set")
        return problems

    def _param_problems(self) -> list[str]:
        problems: list[str] = []
        layers = [self.params, *(rule.params for rule in self.rules)]
        for kind in {k for layer in layers for k in layer}:
            for layer in layers:
                if kind in layer:
                    problems += _sample_problems(
                        kind, {**sample_params(kind), **layer[kind]}
                    )
        return problems


def sample_params(kind: EdlKind) -> dict[str, Any]:
    """Params that make an item of kind valid when a preset sets none (the
    Director fills in the real ones: the word, the asset)."""
    samples: dict[str, dict[str, Any]] = {
        "overlay": {"asset": "skull"},
        "text_pop": {"text": "WOW"},
        "emoji_pop": {"emoji": "🔥"},
        "sfx": {"asset": "pop_bubble"},
        "music_bed": {"asset": "night_drive"},
        "grade_change": {"look": "bw"},
        "audio_fx": {"effect": "bass_boost"},
        "pan": {"from_x": 0.45, "from_y": 0.5, "to_x": 0.55, "to_y": 0.5},
    }
    return dict(samples.get(kind, {}))


def _sample_problems(kind: EdlKind, params: dict[str, Any]) -> list[str]:
    sample = EdlItem(id=1, t_start=0, t_end=1, kind=kind, params=params, reason="x")
    try:
        parse_item(sample)
    except EdlValidationError as error:
        return [f"params of {kind}: {problem}" for problem in error.problems]
    return []


def load_preset(path: Path) -> PresetDef:
    """Return the preset in path; ValueError if it is not a valid preset."""
    try:
        return PresetDef.model_validate(read_yaml(path))
    except ValidationError as exc:
        raise ValueError(f"{path} is not a valid Pro Edit preset: {exc}") from exc


@cache
def load_presets(presets_dir: Path = PRESETS_DIR) -> dict[ProEditPreset, PresetDef]:
    """Return every preset by its ProEditPreset id; ValueError if a file is
    invalid, is not named after an id, or an id has no file."""
    ids = set(get_args(ProEditPreset))
    found = {path.stem: path for path in sorted(presets_dir.glob("*.yaml"))}
    if set(found) != ids:
        raise ValueError(
            f"{presets_dir} must hold one file per preset ({', '.join(sorted(ids))}),"
            f" not {', '.join(found)}"
        )
    return {
        cast(ProEditPreset, name): load_preset(path) for name, path in found.items()
    }


def get_preset(preset: ProEditPreset) -> PresetDef:
    """Return the definition of preset."""
    return load_presets()[preset]
