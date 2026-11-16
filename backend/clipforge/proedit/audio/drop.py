"""The moves around a music drop (SPEC-v3 3.3): a riser before it, 100-300 ms
of silence just before it, an impact and a bass drop on it.

drop_moves adds them to a plan for a drop at a clip second: the music bed
that plays over the silence is cut in two around it (the second part
continuing the music where it would be: music_bed.bed_offsets), then a
silence_before_drop ends on the drop's frame, a RISER sound stretched to
end where the silence starts (at most RISER_S long), an IMPACT sound from
the drop and a bass_boost audio_fx over BASS_DROP_S from it (the bass
drop: the bundled pack has no bass drop sound, so the boom's lows and the
music's are raised; docs/decisions.md). A move that would break a rule of
the plan (an SFX stack, an audio_fx overlap) is left out with a note; the
director's post-processing then snaps them and keeps the SFX off the
punchline words like any planned item.
"""

from dataclasses import dataclass
from typing import Any

from clipforge.models import EdlItem, EdlKind, ProEditPlan
from clipforge.proedit.audio.music_bed import bed_offsets, music_beds
from clipforge.proedit.edl import plan_problems, validate_plan
from clipforge.proedit.edl_params import SILENCE_MAX_S, SILENCE_MIN_S
from clipforge.proedit.snap import PlanNote, PlanTiming

DEFAULT_SILENCE_S = 0.2
RISER = "riser_swell"
RISER_S = 1.6
RISER_MIN_S = 0.3
RISER_GAIN_DB = -8.0
IMPACT = "impact_boom"
IMPACT_S = 1.2
IMPACT_GAIN_DB = -3.0
BASS_DROP_S = 0.6
BASS_DROP_AMOUNT = 0.8


@dataclass(frozen=True)
class DropMoves:
    """The plan with the moves around a drop and a note per move left out."""

    plan: ProEditPlan
    notes: list[PlanNote]


def drop_moves(
    plan: ProEditPlan,
    drop: float,
    timing: PlanTiming,
    silence_s: float = DEFAULT_SILENCE_S,
    riser: bool = True,
) -> DropMoves:
    """Return plan (valid) with the moves around a drop at clip second drop
    (to its frame), the silence silence_s long (to the frame, 0.1-0.3 s);
    without riser, no riser leads into it (a sudden drop). Raises
    ValueError if the silence does not fit before the drop or another item
    of the music track is in it."""
    if not SILENCE_MIN_S <= silence_s <= SILENCE_MAX_S:
        raise ValueError(
            f"the silence before a drop lasts {SILENCE_MIN_S:g} to "
            f"{SILENCE_MAX_S:g} s, not {silence_s:g} s"
        )
    fps = timing.fps
    end = round(drop * fps)
    start = end - max(round(silence_s * fps), 1)
    if start < 0 or end >= timing.last_frame:
        raise ValueError(f"a drop at {drop:g} s leaves no room for its silence")
    items = split_beds(plan, start / fps, end / fps)
    next_id = max((item.id for item in items), default=0) + 1
    silence = _item(next_id, "silence_before_drop", start, end, fps, {}, "drop")
    trial = plan.model_copy(update={"items": [*items, silence]})
    problems = plan_problems(trial, timing.duration)
    if problems:
        raise ValueError(f"the silence before the drop: {problems[0]}")
    riser_start = max(start - round(RISER_S * fps), 0)
    impact_end = min(end + round(IMPACT_S * fps), timing.last_frame)
    bass_end = min(end + round(BASS_DROP_S * fps), timing.last_frame)
    moves = [
        _item(
            next_id + 1,
            "sfx",
            riser_start,
            start,
            fps,
            {"asset": RISER, "gain_db": RISER_GAIN_DB, "fit": "stretch"},
            "riser into the drop",
        ),
        _item(
            next_id + 2,
            "sfx",
            end,
            impact_end,
            fps,
            {"asset": IMPACT, "gain_db": IMPACT_GAIN_DB},
            "impact on the drop",
        ),
        _item(
            next_id + 3,
            "audio_fx",
            end,
            bass_end,
            fps,
            {"effect": "bass_boost", "amount": BASS_DROP_AMOUNT},
            "bass drop",
        ),
    ]
    notes = []
    for move in moves:
        if move.kind == "sfx" and move.params["asset"] == RISER:
            if not riser:
                continue
            if (start - riser_start) / fps < RISER_MIN_S:
                notes.append(_left_out(move, "no room for a riser before it"))
                continue
        attempt = trial.model_copy(update={"items": [*trial.items, move]})
        problems = plan_problems(attempt, timing.duration)
        if problems:
            notes.append(_left_out(move, f"it would break a rule: {problems[0]}"))
        else:
            trial = attempt
    ordered = sorted(trial.items, key=lambda i: (i.t_start, i.id))
    return DropMoves(trial.model_copy(update={"items": ordered}), notes)


def split_beds(plan: ProEditPlan, start: float, end: float) -> list[EdlItem]:
    """Return plan's items with each music bed that plays in [start, end)
    cut to before start and from end; the part from end keeps the bed's
    music running (an explicit params.offset) and takes a new id."""
    typed = {bed.id: bed for bed in music_beds(validate_plan(plan, float("inf")))}
    offsets = bed_offsets(list(typed.values()))
    next_id = max((item.id for item in plan.items), default=0) + 1
    items: list[EdlItem] = []
    for item in plan.items:
        if item.id not in typed or not (item.t_start < end and start < item.t_end):
            items.append(item)
            continue
        if item.t_start < start:
            items.append(item.model_copy(update={"t_end": start}))
        if item.t_end > end:
            offset = offsets[item.id] + end - item.t_start
            params = {**item.params, "offset": round(offset, 6)}
            after = {"id": next_id, "t_start": end, "params": params}
            items.append(item.model_copy(update=after))
            next_id += 1
    return items


def _item(
    id: int,
    kind: EdlKind,
    start: int,
    end: int,
    fps: float,
    params: dict[str, Any],
    reason: str,
) -> EdlItem:
    return EdlItem(
        id=id,
        kind=kind,
        t_start=start / fps,
        t_end=end / fps,
        params=params,
        reason=reason,
        source="auto",
    )


def _left_out(move: EdlItem, why: str) -> PlanNote:
    return PlanNote(
        move.id, move.kind, "dropped", f"{move.reason} left out: {why}", move.t_start
    )
