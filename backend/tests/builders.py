"""Builders of video, transcript, signal and clip data for tests (tests only)."""

from collections.abc import Sequence
from typing import Any

from clipforge.models import (
    CleanupSuggestion,
    Clip,
    CropKeyframe,
    CropPlan,
    CropWindow,
    Scores,
    Segment,
    SignalEvent,
    SignalKind,
    SourceMeta,
    TrackItem,
    Transcript,
    Word,
)
from clipforge.timeline import timeline_of


def word(text: str, start: float, end: float | None = None) -> Word:
    """Return a word of S0 that lasts until end, or else for 0.2 s."""
    end = start + 0.2 if end is None else end
    return Word(text=text, start=start, end=end, speaker="S0", prob=0.9)


def cleanup_item(
    start: float, end: float, kind: str, text: str = ""
) -> CleanupSuggestion:
    """Return a cleanup suggestion of kind ("filler", "pause" or "bad_take")."""
    return CleanupSuggestion.model_validate(
        {"start": start, "end": end, "kind": kind, "text": text}
    )


def said(*timed: tuple[str, float, float]) -> Transcript:
    """Return a transcript of one segment of the words timed (text, start, end)."""
    words = [word(*one) for one in timed]
    text = " ".join(one.text for one in words)
    spoken = Segment(
        id=0,
        start=words[0].start,
        end=words[-1].end,
        text=text,
        words=words,
        speaker="S0",
    )
    return Transcript(language="en", duration=60.0, segments=[spoken])


def segment(segment_id: int, text: str, starts: Sequence[float], end: float) -> Segment:
    """Return a segment of S0 whose words are those of text, each one starting
    at its time in starts and lasting until the next one (the last until end)."""
    ends = [*starts[1:], end]
    words = [word(*timed) for timed in zip(text.split(), starts, ends, strict=True)]
    return Segment(
        id=segment_id, start=starts[0], end=end, text=text, words=words, speaker="S0"
    )


# Six words of the clip 10-12.5 s (make_clip): "Wait," ends with a comma, "my
# brother ate the" have no break, and a pause of 0.45 s comes before "pizza.".
SIX = Segment(
    id=0,
    start=10.0,
    end=12.2,
    text="Wait, my brother ate the pizza.",
    words=[
        word("Wait,", 10.0, 10.3),
        word("my", 10.36, 10.5),
        word("brother", 10.54, 10.8),
        word("ate", 10.84, 11.1),
        word("the", 11.14, 11.25),
        word("pizza.", 11.7, 12.2),
    ],
    speaker="S0",
)


def event(
    kind: SignalKind, start: float, end: float, intensity: float = 1.0
) -> SignalEvent:
    """Return a signal event of this kind."""
    return SignalEvent(kind=kind, start=start, end=end, intensity=intensity)


def cut(time: float) -> SignalEvent:
    """Return a scene cut at time."""
    return event("scene_cut", time, time)


# The laughs that the signals step finds in fixtures/sample.mp4 (decisions.md).
FIXTURE_LAUGHS = (
    event("laugh", 14.16, 16.08, 0.758),
    event("laugh", 33.36, 34.8, 0.847),
    event("laugh", 52.08, 54.48, 0.738),
)


def source_meta(
    start: float = 0.0, end: float = 60.0, duration: float | None = None
) -> SourceMeta:
    """Return the meta.json of a 1280x720 30 fps video whose timeframe runs
    from start to end seconds; the video lasts duration, by default end."""
    return SourceMeta(
        title="sample",
        duration=end if duration is None else duration,
        width=1280,
        height=720,
        fps=30.0,
        timeframe_start=start,
        timeframe_end=end,
    )


def make_clip(template: str, **changes: Any) -> Clip:
    """Return clip 7 (10-12.5 s) with template and the hook "He ate it all";
    changes replace any of its fields, and start or end set the span of its
    single segment (and its video track)."""
    scores = Scores(overall=80, hook=80, flow=80, value=80, trend=80, laugh=0, energy=0)
    span = (changes.pop("start", 10.0), changes.pop("end", 12.5))
    fields: dict[str, Any] = {
        "id": 7,
        "project_id": 1,
        "segments": [span],
        "tracks": timeline_of([span]),
        "title": "Pizza",
        "hook_text": "He ate it all",
        "description": "",
        "hashtags": ["food", "pizza", "funny"],
        "emphasis_words": ["brother"],
        "reason": "",
        "scores": scores,
        "layout": "fill",
        "caption_template": template,
        "caption_overrides": [],
        "cut_ranges": [],
        "status": "candidate",
        "output_path": None,
    }
    return Clip.model_validate(fields | changes)


def plan_at(*xs: int) -> CropPlan:
    """A 404x720 fill window (9:16 of 1280x720) whose left edge is xs[k] at
    10 + k seconds."""
    keyframes = [CropKeyframe(t=10.0 + k, x=x, faces=[]) for k, x in enumerate(xs)]
    window = CropWindow(width=360, height=360, y=0, xs=list(xs))
    return CropPlan(
        clip_id=7,
        start=10.0,
        end=10.0 + len(xs) - 1,
        aspect="9:16",
        width=404,
        height=720,
        y=0,
        keyframes=keyframes,
        layout="fill",
        split=(window, window),
    )


def track_item(
    item_id: str, kind: str, start: float, end: float, **fields: Any
) -> TrackItem:
    """Return a timeline track item; fields set its asset_id and props."""
    return TrackItem.model_validate(
        {"id": item_id, "kind": kind, "start": start, "end": end} | fields
    )
