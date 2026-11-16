"""Duplicate a clip and split one clip into two (SPEC-v2 3.5).

duplicate_clip adds a clip that is a copy of a clip, with new ids for its
track items, ready to edit on its own (a candidate, not rendered yet).

split_clip splits a clip at a time of the source (frame_at snaps it to a
frame of the clip): the clip keeps the sections that play before it and a
new clip (the second part) gets the ones that play after it, a section
that holds the time being cut in two. Everything of the clip that has a
time goes where its time is: cut ranges (cut at the time), caption
overrides and marks, zoom and crop keyframes, scenes, and the layer items
(these are timed in the rendered clip, so they follow the time that the
first part lasts). The two parts last as long as the clip did, to a frame
when the time is on a frame of the clip's start and its sections are in
source order without gaps.
"""

import secrets
from collections.abc import Callable, Mapping, Sequence

from sqlmodel import Session

from clipforge import config
from clipforge.clip_edit import ClipEditError, section_problems
from clipforge.db import ClipRow
from clipforge.models import (
    Clip,
    CutRange,
    SourceSpan,
    Timeline,
    TrackItem,
    TrackName,
)
from clipforge.pipeline.scenes import fit_scenes
from clipforge.pipeline.sections import fit_cuts, played_spans
from clipforge.timeline import LAYER_TRACKS, clip_length, with_segments

# The kinds of item that play an asset from an offset.
_OFFSET_KINDS = frozenset({"video", "audio"})


def duplicate_clip(
    session: Session, row: ClipRow, changes: Mapping[str, object] | None = None
) -> ClipRow:
    """Add a copy of the clip row to session's database, commit and return
    it: a new candidate clip of the same project with the same sections,
    edits and tracks (new ids for the layer items), its title ending in
    " (copy)", and no render. changes, if given, replace fields of the copy
    (a Pro Edit variant's title, parent, variant and status)."""
    clip = row.to_model()
    tracks = clip.tracks.model_copy(
        update={
            name: [_new_id(item, name) for item in getattr(clip.tracks, name)]
            for name in LAYER_TRACKS
        }
    )
    copied = {"tracks": tracks, "title": f"{clip.title} (copy)"}
    return _add(session, clip, copied | dict(changes or {}))


def split_clip(
    session: Session, row: ClipRow, at: float, duration: float
) -> tuple[ClipRow, ClipRow]:
    """Split the clip row at at seconds of the source, in session, and commit;
    return the row (now the first part) and the new row of the second part.

    The second part is a candidate with no hook and its title ending in
    " (part 2)". Raises ClipEditError, and changes nothing, if at is not
    inside a section or on the edge between two, or if either part would not
    be valid in a source of duration seconds.
    """
    clip, fps = row.to_model(), config.settings.render.fps
    at = frame_at(clip, at, fps)
    first, second = split_sections(clip.segments, at)
    first_length = clip_length(
        _with(clip, first, fit_cuts(clip.cut_ranges, first)), fps
    )
    parts = [
        _part_fields(clip, first, (0, first_length)),
        _part_fields(clip, second, (first_length, clip_length(clip, fps))),
    ]
    for segments, fields in zip((first, second), parts, strict=True):
        part = clip.model_copy(update=fields)
        problems = section_problems(segments, duration, fps)
        if not problems and not played_spans(
            part.start, part.end, segments, part.cut_ranges, fps
        ):
            problems.append("the cut ranges leave nothing of a part of the clip")
        if problems:
            raise ClipEditError("; ".join(problems))
    added = _add(
        session,
        clip,
        parts[1] | {"title": f"{clip.title} (part 2)", "hook_text": ""},
    )
    for name, value in parts[0].items():
        setattr(row, name, value)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row, added


def frame_at(clip: Clip, at: float, fps: int) -> float:
    """Return at, seconds of the source, moved to the nearest frame of the
    clip at fps frames a second, counted from its start."""
    return round(clip.start + round((at - clip.start) * fps) / fps, 6)


def split_sections(
    segments: Sequence[SourceSpan], at: float
) -> tuple[list[SourceSpan], list[SourceSpan]]:
    """Return the sections that play before and those that play after at
    seconds of the source: a section that holds at is cut in two there. Raises
    ClipEditError if no section holds at (inside it) and at is not the edge
    between two sections in play order."""
    for index, (start, end) in enumerate(segments):
        if start < at < end:
            return (
                [*segments[:index], (start, at)],
                [(at, end), *segments[index + 1 :]],
            )
    for index, (start, end) in enumerate(segments):
        if at == start and index > 0:
            return list(segments[:index]), list(segments[index:])
        if at == end and index < len(segments) - 1:
            return list(segments[: index + 1]), list(segments[index + 1 :])
    raise ClipEditError(f"no section plays {at:g} s of the video (inside it)")


def _add(session: Session, clip: Clip, changes: dict[str, object]) -> ClipRow:
    """Add a candidate clip row, in session, with clip's fields (but its
    id, status and render) replaced by changes; commit and return it."""
    fields = {name: getattr(clip, name) for name in Clip.model_fields if name != "id"}
    added = ClipRow(**(fields | {"status": "candidate", "output_path": None} | changes))
    session.add(added)
    session.commit()
    session.refresh(added)
    return added


def _with(clip: Clip, segments: Sequence[SourceSpan], cuts: list[CutRange]) -> Clip:
    """Return clip with segments as its sections and cuts as its cut ranges."""
    return clip.model_copy(update={"segments": list(segments), "cut_ranges": cuts})


def _part_fields(
    clip: Clip,
    segments: Sequence[SourceSpan],
    window: tuple[float, float],
) -> dict[str, object]:
    """Return the fields of the part of clip that plays segments (one side of
    a split), which plays from window[0] to window[1] seconds of the clip's
    render: what has a time, kept where it belongs to the part."""
    start, end = min(s for s, _ in segments), max(e for _, e in segments)
    inside = _inside(segments)
    style = clip.caption_style
    if style.word_marks is not None:
        style = style.model_copy(
            update={"word_marks": [m for m in style.word_marks if inside(m.start)]}
        )
    framing = clip.framing.model_copy(
        update={"points": [p for p in clip.framing.points if inside(p.t, True)]}
    )
    return {
        "segments": list(segments),
        "tracks": with_segments(_window_tracks(clip.tracks, *window), segments),
        "cut_ranges": fit_cuts(clip.cut_ranges, segments),
        "caption_overrides": [w for w in clip.caption_overrides if inside(w.start)],
        "caption_style": style,
        "framing": framing,
        "zoom_keyframes": [k for k in clip.zoom_keyframes if inside(k.t, True)],
        "scene_reframes": fit_scenes(clip.scene_reframes, start, end),
    }


def _inside(segments: Sequence[SourceSpan]) -> Callable[..., bool]:
    """Return a function that says whether a time of the source is in a
    section of segments: from start up to its end, or with closed=True
    including its end."""

    def inside(time: float, closed: bool = False) -> bool:
        return any(
            start <= time < end or (closed and time == end) for start, end in segments
        )

    return inside


def _window_tracks(tracks: Timeline, begin: float, end: float) -> Timeline:
    """Return tracks with only what shows from begin to end seconds of the
    clip's render, from 0 on: items cut at the window's edges, and a played
    asset starting where it was when it is cut at the start."""
    fps = config.settings.render.fps
    changes: dict[str, list[TrackItem]] = {}
    for name in LAYER_TRACKS:
        items = [_cut(item, begin, end) for item in getattr(tracks, name)]
        changes[name] = [
            item
            for item in items
            if item is not None and item.end - item.start >= 1 / fps
        ]
    return tracks.model_copy(update=changes)


def _cut(item: TrackItem, begin: float, end: float) -> TrackItem | None:
    """Return item cut to begin..end and moved so begin is 0, or None if it
    does not show then."""
    if item.end <= begin or item.start >= end:
        return None
    start = max(item.start, begin)
    props = dict(item.props)
    if item.kind in _OFFSET_KINDS and start > item.start:
        props["offset"] = props.get("offset", 0) + start - item.start
    return item.model_copy(
        update={
            "start": round(start - begin, 6),
            "end": round(min(item.end, end) - begin, 6),
            "props": props,
        }
    )


def _new_id(item: TrackItem, track: TrackName) -> TrackItem:
    """Return item with a new id: the track's name and a random suffix."""
    return item.model_copy(update={"id": f"{track}-{secrets.token_hex(4)}"})
