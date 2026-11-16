"""The Skull Moment sequence of the rule-based Director (SPEC-v3 3.4).

At the "caught" moment, the first frame after the punchline word, the
picture freezes, turns black and white (or dark), a skull pops on the
face, it punches in and shakes, an impact and a bass drop hit (with the
silence before it over a music bed), the picture holds, then snaps back to
color with a whoosh. The hold is the preset's hold_s, longer up to
HOLD_MAX_S so that the whoosh is one SFX spacing after the impact at the
intensity, and shorter (down to HOLD_MIN_S) to leave room for the whoosh
before the clip ends; with less room there is no Skull Moment there.

The sequence is one move (composites.py): the budgets count it once, and
every step (freeze, look, skull, punch, shake, impact and bass drop,
whoosh) must fit or the whole Skull Moment is left out with a note that
names the step that did not fit. Only the silence before the drop is
optional (left out with a note when the music bed cannot take it).
"""

import math
from typing import Any

from clipforge.models import EdlKind
from clipforge.proedit.audio.sfx_place import WHOOSH_GAIN_DB
from clipforge.proedit.director_build import PlanBuilder, Snapshot
from clipforge.proedit.director_moments import Moment
from clipforge.proedit.director_moves import bass_drop, move_params
from clipforge.proedit.preset_defs import PresetDef
from clipforge.proedit.snap import EPSILON

HOLD_MIN_S = 1.0
HOLD_MAX_S = 2.0
SHAKE_MAX_S = 0.5
SNAP_BACK_WHOOSH = "whoosh_swift"
SNAP_BACK_WHOOSH_S = 0.3
SKULL_SCALE = 0.35


def skull_hold(builder: PlanBuilder, preset: PresetDef, at: float) -> float | None:
    """The hold in seconds of a Skull Moment at clip second at (module
    docstring), on whole frames; None when it does not fit."""
    assert preset.skull is not None
    fps = builder.timing.fps
    spacing = builder.budget.kinds["sfx"].window_s
    wanted = min(HOLD_MAX_S, max(preset.skull.hold_s, spacing))
    room = builder.timing.duration - at - SNAP_BACK_WHOOSH_S
    hold = math.floor(min(wanted, room) * fps + EPSILON) / fps
    return hold if hold >= HOLD_MIN_S - EPSILON else None


def skull_moment(builder: PlanBuilder, moment: Moment, preset: PresetDef) -> bool:
    """Place the Skull Moment after moment's word (module docstring);
    return whether it was placed."""
    assert preset.skull is not None
    fps = builder.timing.fps
    at = math.ceil(moment.end * fps - EPSILON) / fps
    hold = skull_hold(builder, preset, at)
    what = f"the caught moment after {moment.what}"
    if hold is None:
        why = f"less than {HOLD_MIN_S:g} s of hold fits before the clip end"
        builder.leave_out("skull_moment", at, f"skull moment on {what}", why)
        return False
    return place_skull(builder, at, at + hold, moment, preset, what)


def place_skull(
    builder: PlanBuilder,
    at: float,
    end: float,
    moment: Moment,
    preset: PresetDef,
    what: str,
) -> bool:
    """Place every step of a Skull Moment frozen from at to end on what (a
    description of the moment), or none of them and a LeftOut that names
    the step that did not fit; return whether it was placed."""
    assert preset.skull is not None
    spec = preset.skull
    before = builder.snapshot()
    punch = move_params("zoom_punch", moment, preset, None, len(builder.items))
    shake = move_params("shake", moment, preset, None, len(builder.items))
    skull = {"asset": spec.overlay, "anchor": "face", "scale": SKULL_SCALE}
    whoosh = {"asset": SNAP_BACK_WHOOSH, "gain_db": WHOOSH_GAIN_DB, "fit": "stretch"}
    shake_end = at + min(SHAKE_MAX_S, end - at)
    look = ({"look": spec.look}, f"instant {spec.look} look on the freeze")
    steps: list[tuple[EdlKind, float, float, dict[str, Any], str]] = [
        ("freeze_frame", at, end, {}, f"freeze on {what}"),
        ("grade_change", at, end, *look),
        ("overlay", at, end, skull, f"{spec.overlay} on the face at {what}"),
        ("zoom_punch", at, end, punch or {}, f"punch-in on the face at {what}"),
        ("shake", at, shake_end, shake or {}, f"shake on the hit at {what}"),
    ]
    for kind, start, stop, params, reason in steps:
        item, why = builder.fit(kind, start, stop, params, reason)
        if item is None:
            return _left_out(
                builder, before, at, what, f"its {kind} did not fit: {why}"
            )
    if not bass_drop(builder, at, what, riser=False):
        why = builder.left_out[-1].why
        return _left_out(builder, before, at, what, f"its bass drop did not fit: {why}")
    snap_back = "whoosh on the snap back to color"
    item, why = builder.fit("sfx", end, end + SNAP_BACK_WHOOSH_S, whoosh, snap_back)
    if item is None:
        return _left_out(builder, before, at, what, f"its whoosh did not fit: {why}")
    return True


def _left_out(
    builder: PlanBuilder, before: Snapshot, at: float, what: str, why: str
) -> bool:
    builder.restore(before)
    builder.leave_out("skull_moment", at, f"skull moment on {what}", why)
    return False
