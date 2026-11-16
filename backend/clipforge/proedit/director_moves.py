"""The moves of the rule-based Director (SPEC-v3 3.3-3.5): an edit decision
of one kind at a Moment, and the bass drop composite.

A move's window: a transition is centred on its moment (the cut); a setup
push or a payoff reveal spans its moment; slow motion, speed ramps, freezes
and reveals of a punchline start when the word ends (the reaction); every
other move starts at the moment and lasts the preset's length of its kind
(DEFAULT_LENGTHS otherwise; an SFX lasts its sound, a text pop its word).
A kind with a beat length in the preset that starts on a beat of the music
ends that many beats later instead (beat_end), so its end is on a beat too.
Params are the preset's, then the rule's, then what the moment gives (the
word's text or emoji, the next overlay of the preset's set, a seed).
"""

import bisect
from typing import Any

from clipforge.models import EdlItem, EdlKind
from clipforge.proedit.audio.drop import (
    BASS_DROP_AMOUNT,
    BASS_DROP_S,
    IMPACT,
    IMPACT_GAIN_DB,
    IMPACT_S,
    RISER,
    drop_moves,
)
from clipforge.proedit.audio.sounds import bundled_named
from clipforge.proedit.director_build import PlanBuilder
from clipforge.proedit.director_moments import Moment, letters
from clipforge.proedit.edl import TRACK_OF_KIND
from clipforge.proedit.preset_defs import PresetDef, Rule, sample_params
from clipforge.proedit.snap import END_ANCHORED, EPSILON, snap_target

DEFAULT_LENGTHS: dict[EdlKind, float] = {
    "zoom_punch": 0.6,
    "zoom_push": 2.0,
    "zoom_out_reveal": 0.8,
    "pan": 2.0,
    "shake": 0.3,
    "flash": 0.15,
    "glitch": 0.25,
    "rgb_split": 0.3,
    "freeze_frame": 0.8,
    "speed_ramp": 0.8,
    "slowmo": 1.0,
    "transition": 0.3,
    "grade_change": 1.0,
    "overlay": 1.2,
    "text_pop": 0.9,
    "emoji_pop": 0.9,
    "sfx": 1.0,
    "audio_fx": 0.6,
}
AFTER_PUNCHLINE: frozenset[EdlKind] = frozenset(
    {"slowmo", "speed_ramp", "freeze_frame", "zoom_out_reveal"}
)
SPANNING: frozenset[EdlKind] = frozenset({"zoom_push", "zoom_out_reveal"})
SEEDED: frozenset[EdlKind] = frozenset({"shake", "glitch", "grain"})
TEXT_MAX = 60


def label(kind: str) -> str:
    """The kind as words for a reason ("zoom punch")."""
    return kind.replace("_", " ")


def length_of(kind: EdlKind, preset: PresetDef, params: dict[str, Any]) -> float:
    """How long a move of kind lasts (module docstring)."""
    if kind == "sfx":
        sound = bundled_named(str(params["asset"]))
        if sound is not None:
            return sound.seconds
    return preset.lengths.get(kind, DEFAULT_LENGTHS.get(kind, 1.0))


def move_params(
    kind: EdlKind, moment: Moment, preset: PresetDef, rule: Rule | None, n: int
) -> dict[str, Any] | None:
    """The params of a move of kind at moment (module docstring), n
    counting the preset's moves; None when the moment cannot give what the
    kind needs (a text pop without a word, an emoji pop without an emoji)."""
    params = {
        **preset.params.get(kind, {}),
        **(rule.params.get(kind, {}) if rule else {}),
    }
    if kind == "text_pop" and "text" not in params:
        if moment.word is None or not letters(moment.word.text):
            return None
        params["text"] = letters(moment.word.text).upper()[:TEXT_MAX]
    if kind == "emoji_pop" and "emoji" not in params:
        if moment.word is None or moment.word.emoji is None:
            return None
        params["emoji"] = moment.word.emoji
    if kind == "overlay" and "asset" not in params:
        params["asset"] = preset.overlays[n % len(preset.overlays)]
    if kind in SEEDED:
        params.setdefault("seed", n)
    return {**sample_params(kind), **params}


def move_window(kind: EdlKind, moment: Moment, length: float) -> tuple[float, float]:
    """The planned start and end of a move of kind at moment."""
    if kind == "transition":
        return moment.t - length / 2, moment.t + length / 2
    if kind in SPANNING and moment.signal in ("setup", "payoff"):
        return moment.t, max(moment.end, moment.t + length)
    if kind in AFTER_PUNCHLINE and moment.signal == "punchline":
        return moment.end, moment.end + length
    if kind == "text_pop" and moment.word is not None:
        return moment.t, max(moment.end, moment.t + length)
    return moment.t, moment.t + length


def place_kind(
    builder: PlanBuilder,
    kind: EdlKind,
    moment: Moment,
    preset: PresetDef,
    rule: Rule | None,
    record: bool = True,
) -> EdlItem | None:
    """Place a move of kind at moment (module docstring); return its item,
    or None when it was left out."""
    reason = f"{label(kind)} on {moment.what}"
    params = move_params(kind, moment, preset, rule, len(builder.items))
    if params is None:
        if record:
            builder.leave_out(
                kind, moment.t, reason, f"{moment.what} gives no {label(kind)}"
            )
        return None
    start, end = move_window(kind, moment, length_of(kind, preset, params))
    end = beat_end(builder, kind, preset, start, end)
    return builder.place(kind, start, end, params, reason, record)


def beat_end(
    builder: PlanBuilder, kind: EdlKind, preset: PresetDef, start: float, end: float
) -> float:
    """Return the planned end of a move of kind from start to end: when the
    preset gives kind a beat length and the move snaps to a beat, the beat
    that many beats after it, less the distance the snap moves the start
    (the builder then places the move from that beat to this one); else
    end (also when the music ends before that beat)."""
    count = preset.beat_lengths.get(kind)
    beats = builder.timing.beats
    if count is None or not beats or kind in END_ANCHORED:
        return end
    anchor = snap_target(start, builder.snap_modes[kind], builder.timing)
    index = bisect.bisect_left(beats, anchor - EPSILON)
    if index + count >= len(beats) or abs(beats[index] - anchor) > EPSILON:
        return end
    return start + beats[index + count] - anchor


def bass_drop(builder: PlanBuilder, at: float, what: str, riser: bool = True) -> bool:
    """Place an impact and a bass drop at clip second at (to its frame);
    over a music bed also the silence before it and, with riser, a riser
    into it (audio/drop.drop_moves). The impact and the bass drop are one
    move (composites.py): both fit or the drop is left out whole with a
    note; the silence and the riser are left out with a note when they do
    not fit. Return whether the drop was placed."""
    before = builder.snapshot()
    reason = f"impact on {what}"
    impact_params = {"asset": IMPACT, "gain_db": IMPACT_GAIN_DB}
    impact = builder.candidate("sfx", at, at + IMPACT_S, impact_params, reason)
    why = "it has no frame in the clip" if impact is None else builder.problem(impact)
    if impact is None or why is not None:
        builder.leave_out("bass_drop", at, f"bass drop on {what}", why or "")
        return False
    extras = _drop_extras(builder, impact.t_start, what, riser)
    builder.add(impact)
    bass = {"effect": "bass_boost", "amount": BASS_DROP_AMOUNT}
    end = impact.t_start + BASS_DROP_S
    boost, why = builder.fit(
        "audio_fx", impact.t_start, end, bass, f"bass drop on {what}"
    )
    if boost is None:
        builder.restore(before)
        builder.leave_out(
            "bass_drop", at, f"bass drop on {what}", f"its bass boost: {why}"
        )
        return False
    for move in extras:
        text = f"{move.reason} on {what}"
        builder.place(move.kind, move.t_start, move.t_end, move.params, text)
    return True


def _drop_extras(
    builder: PlanBuilder, at: float, what: str, riser: bool
) -> list[EdlItem]:
    """Over a music bed: split the bed around a silence that ends at at and
    return the riser to place (drop_moves); nothing without a bed."""
    if not any(i.kind == "music_bed" for i in builder.items):
        return []
    try:
        dropped = drop_moves(builder.plan(), at, builder.timing, riser=riser)
    except ValueError as error:
        builder.leave_out(
            "silence_before_drop", at, f"silence before {what}", str(error)
        )
        return []
    known = {i.id for i in builder.items}
    music = [i for i in dropped.plan.items if TRACK_OF_KIND[i.kind] == "music"]
    builder.replace(
        [*(i for i in builder.items if TRACK_OF_KIND[i.kind] != "music"), *music]
    )
    return [
        i
        for i in dropped.plan.items
        if i.id not in known and i.kind == "sfx" and i.params.get("asset") == RISER
    ]
