"""Shared helpers of the Pro Edit EDL post-processing tests."""

from typing import Any

from clipforge.models import EdlItem, EdlKind, EdlSource, ProEditIntensity, ProEditPlan

PARAMS: dict[str, dict[str, Any]] = {
    "sfx": {"asset": "whoosh"},
    "text_pop": {"text": "WOW"},
    "overlay": {"asset": "skull"},
    "grade_change": {"look": "bw"},
    "music_bed": {"asset": "bed"},
}


def item(
    id: int,
    kind: EdlKind,
    t_start: float,
    t_end: float,
    source: EdlSource = "auto",
    params: dict[str, Any] | None = None,
) -> EdlItem:
    return EdlItem(
        id=id,
        kind=kind,
        t_start=t_start,
        t_end=t_end,
        params=PARAMS.get(kind, {}) if params is None else params,
        reason="test",
        source=source,
    )


def times(items: list[EdlItem]) -> dict[int, tuple[float, float]]:
    return {i.id: (i.t_start, i.t_end) for i in items}


def plan(items: list[EdlItem], intensity: ProEditIntensity) -> ProEditPlan:
    return ProEditPlan(
        id=1,
        clip_id=1,
        preset="phonk_edit",
        intensity=intensity,
        version=1,
        items=items,
        created_by="rule_director",
    )
