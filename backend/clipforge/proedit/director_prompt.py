"""The messages of the LLM Director (SPEC-v3 3.5) and the reply it must send.

The system prompt is prompts/proedit_director.md with DirectorReply's JSON
Schema and the params schema of every kind the preset allows. The user
message is one compact JSON object: the clip's signals (times in rendered
clip seconds, rounded to the millisecond; face tracks as their mean box,
not their samples), the transcript as [start, end, word, emphasis] rows,
the music bed's beat grid, the preset's rules and look, the intensity and
its budget, the style recipe's targets, the campaign's constraints and the
asset catalog (ids and tags only). A retry adds the problems of the
previous reply.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Any, get_args

from pydantic import BaseModel, ConfigDict, Field

from clipforge.models import (
    Campaign,
    EdlKind,
    ProEditIntensity,
    ProEditPlan,
    ProEditPreset,
    StyleRecipe,
)
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, fill
from clipforge.proedit.budgets import effective_budget
from clipforge.proedit.composites import Composite
from clipforge.proedit.director_catalog import ITEM_KIND, CatalogAsset
from clipforge.proedit.director_music import MusicChoice
from clipforge.proedit.edl import TRACK_OF_KIND, TypedEdlItem
from clipforge.proedit.preset_defs import PresetDef
from clipforge.proedit.signal_models import FaceTrackSignal, ProEditSignals
from clipforge.proedit.style.recipe import director_recipe

PROMPT = PROMPTS_DIR / "proedit_director.md"
DIGITS = 3
COMPACT = (",", ":")


class DirectorItem(BaseModel):
    """One edit decision of the reply; the code numbers the items."""

    model_config = ConfigDict(extra="forbid")

    kind: EdlKind
    t_start: float = Field(ge=0)
    t_end: float = Field(gt=0)
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=1)


class DirectorMoment(BaseModel):
    """A composite move the reply asks for at clip second t (a Skull Moment
    or a bass drop); the code places its items (director_expand)."""

    model_config = ConfigDict(extra="forbid")

    move: Composite
    t: float = Field(ge=0)
    reason: str = Field(min_length=1)


class DirectorReply(BaseModel):
    """The Director's plan: a short rationale, the edit decisions and the
    composite moves for the code to place."""

    model_config = ConfigDict(extra="forbid")

    rationale: str = Field(min_length=1)
    items: list[DirectorItem]
    moments: list[DirectorMoment] = Field(default_factory=list)


@dataclass(frozen=True)
class DirectorRequest:
    """What a plan is made from: the clip's signals, the preset (named
    preset_id) and intensity, the bed the caller chose, the style recipe
    and campaign it aims for, the assets it may use, the id and version
    the plan gets, and whether it ends on a loop-friendly ending
    (proedit/retention.py)."""

    signals: ProEditSignals
    preset: PresetDef
    preset_id: ProEditPreset
    intensity: ProEditIntensity
    music: MusicChoice | None = None
    recipe: StyleRecipe | None = None
    campaign: Campaign | None = None
    catalog: tuple[CatalogAsset, ...] = ()
    plan_id: int = 0
    version: int = 1
    loop_ending: bool = False


def params_models() -> dict[EdlKind, type[BaseModel]]:
    """Return the params model of every kind (from edl.TypedEdlItem)."""
    union = get_args(TypedEdlItem)[0]
    models: dict[EdlKind, type[BaseModel]] = {}
    for item in get_args(union):
        (kind,) = get_args(item.model_fields["kind"].annotation)
        models[kind] = item.model_fields["params"].annotation
    return models


def system_prompt(preset: PresetDef) -> str:
    """Return the system prompt for a plan of preset."""
    models = params_models()
    params = {kind: models[kind].model_json_schema() for kind in sorted(preset.kinds)}
    tracks = {kind: TRACK_OF_KIND[kind] for kind in sorted(preset.kinds)}
    return fill(
        PROMPT,
        {
            "schema": json.dumps(DirectorReply.model_json_schema(), indent=2),
            "params": json.dumps(params, separators=COMPACT, ensure_ascii=False),
            "tracks": json.dumps(tracks, separators=COMPACT),
        },
    )


def _r(t: float) -> float:
    return round(t, DIGITS)


def _span(start: float, end: float) -> list[float]:
    return [_r(start), _r(end)]


def _face(track: FaceTrackSignal) -> dict[str, Any]:
    box = None
    if track.samples:
        box = [
            _r(fmean(getattr(s, side) for s in track.samples))
            for side in ("x", "y", "width", "height")
        ]
    return {
        "track": track.track,
        "span": _span(track.start, track.end),
        "subject_share": _r(track.subject_share),
        "mean_box": box,
    }


def compact_signals(
    signals: ProEditSignals, music: MusicChoice | None
) -> dict[str, Any]:
    """Return the signals of the clip (and the bed's grid) as the compact
    JSON object the Director reads."""
    duration = signals.duration
    bed = None
    if music is not None:
        bed = {
            "asset": music.asset,
            "offset": _r(music.offset),
            "bpm": None if music.grid.bpm is None else _r(music.grid.bpm),
            "beats": [_r(t) for t in music.beats(duration)],
            "downbeats": [_r(t) for t in music.downbeats(duration)],
        }
    return {
        "clip": {
            "duration": _r(duration),
            "fps": signals.fps,
            "width": signals.width,
            "height": signals.height,
        },
        "transcript": [
            [_r(w.start), _r(w.end), w.text, int(w.emphasis)] for w in signals.words
        ],
        "emoji_marks": {
            str(n): w.emoji for n, w in enumerate(signals.words) if w.emoji
        },
        "speaker_turns": [
            [t.speaker, *_span(t.start, t.end)] for t in signals.speaker_turns
        ],
        "sentences": [_span(s.start, s.end) for s in signals.sentences],
        "punchlines": [
            {
                "word": p.text,
                "span": _span(p.start, p.end),
                "reaction_at": _r(p.at),
                "reaction": p.kind,
                "intensity": _r(p.intensity),
            }
            for p in signals.punchlines
        ],
        "events": [
            [e.kind, *_span(e.start, e.end), _r(e.intensity)] for e in signals.events
        ],
        "scene_cuts": [_r(t) for t in signals.scene_cuts],
        "silences": [_span(s.start, s.end) for s in signals.silences],
        "pauses": [_span(s.start, s.end) for s in signals.pauses],
        "faces": [_face(track) for track in signals.faces],
        "motion_spans": [
            [*_span(m.start, m.end), _r(m.level)] for m in signals.motion_spans
        ],
        "music": bed,
    }


def _preset(request: DirectorRequest) -> dict[str, Any]:
    preset = request.preset
    look = preset.model_dump(
        mode="json",
        include={"caption_style", "grade", "vignette", "grain"},
        exclude_none=True,
    )
    return {
        "id": request.preset_id,
        "name": preset.name,
        "description": preset.description,
        "kinds": sorted(preset.kinds),
        "look": look,
        "params": preset.model_dump(mode="json")["params"],
        "lengths_s": preset.lengths,
        "music": preset.music.model_dump(mode="json"),
        "overlays": preset.overlays,
        "rules": [rule.model_dump(mode="json") for rule in preset.rules],
        "pattern_interrupts": preset.interrupts,
        "skull": None if preset.skull is None else preset.skull.model_dump(mode="json"),
    }


def _budget(request: DirectorRequest) -> dict[str, Any]:
    budget = effective_budget(
        request.intensity, request.preset.budgets.get(request.intensity)
    )
    return {
        "kinds": {
            kind: f"at most {d.count} per {d.window_s:g} s"
            for kind, d in sorted(budget.kinds.items())
            if kind in request.preset.kinds
        },
        "effects": f"at most {budget.effects.count} per {budget.effects.window_s:g} s",
        "pattern_interrupt_every_s": budget.interrupt_s,
    }


def _catalog(request: DirectorRequest) -> list[dict[str, Any]]:
    usable = {ITEM_KIND[k] for k in request.preset.kinds if k in ITEM_KIND}
    return [
        entry.model_dump(mode="json")
        for entry in request.catalog
        if entry.kind in usable
    ]


def director_input(request: DirectorRequest) -> dict[str, Any]:
    """Return everything the Director reads, as one JSON object."""
    recipe = request.recipe
    campaign = request.campaign
    return {
        "signals": compact_signals(request.signals, request.music),
        "preset": _preset(request),
        "intensity": request.intensity,
        "budget": _budget(request),
        "style_recipe": None if recipe is None else director_recipe(recipe),
        "campaign": None
        if campaign is None
        else {
            "allow_heavy_edits": campaign.allow_heavy_edits,
            "banned_content_notes": campaign.banned_content_notes,
        },
        "asset_catalog": _catalog(request),
    }


def user_prompt(request: DirectorRequest, problems: Sequence[str] = ()) -> str:
    """Return the user message; problems, the previous reply's, ask for a
    corrected plan."""
    data = json.dumps(director_input(request), separators=COMPACT, ensure_ascii=False)
    text = f"The clip and the edit to plan:\n{data}"
    if not problems:
        return text
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        f"{text}\n\nYour previous reply was not valid (item N is the N-th entry "
        f"of items, from 1):\n{listed}\n\n"
        "Reply again with only the JSON object described in the instructions."
    )


def reply_text(plan: ProEditPlan) -> str:
    """Return plan as the reply that would describe it (to estimate the
    size of a reply)."""
    reply = DirectorReply(
        rationale=plan.rationale or "-",
        items=[
            DirectorItem(
                kind=i.kind,
                t_start=i.t_start,
                t_end=i.t_end,
                params=i.params,
                reason=i.reason,
            )
            for i in plan.items
        ],
    )
    return reply.model_dump_json()
