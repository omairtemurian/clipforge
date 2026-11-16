"""Edits of a clip (PATCH /clips/{id}): check a ClipPatch against the clip
and its source, then apply it to the clip's row.

A patch may move the clip's start and end (its segments' span), change its
text, layout, caption template, caption style and overrides, crop offset,
framing (aspect, fit background, crop tool), cut ranges, auto cut,
auto zoom (its switch and zoom keyframes), scenes and transitions. The result must keep
start < end inside the source video, every cut range inside the clip (with
something left to show), name a caption template that exists and a
caption style font that is bundled, and have scenes that cover the clip
(pipeline/scenes), if any.

Section ops (SPEC-v2 3.5) change the clip's segments, its sections: trim or
extend one (trim_section), add a part of the source (add_section), split
one in two (split_section), delete one (delete_section) or play them in
another order (reorder_sections). Sections never overlap in the source and
last a frame at least (section_problems). apply_sections stores the new
sections with the video track that plays them, the cut ranges that are
still inside them (fit_cuts) and the scenes fitted to the new span.
"""

import math
from collections.abc import Sequence
from itertools import pairwise

from sqlmodel import Session

from clipforge import config
from clipforge.captions_templates import load_templates, style_problems
from clipforge.db import ClipRow
from clipforge.models import ClipPatch, CutRange, SourceSpan
from clipforge.pipeline.scenes import fit_scenes, scene_problems, snap_scenes
from clipforge.pipeline.sections import fit_cuts, played_spans
from clipforge.timeline import respan, with_segments


class ClipEditError(ValueError):
    """A patch would leave a clip invalid; the message says why."""


class SectionNotFound(ClipEditError):
    """A section op names a section index that the clip does not have."""


def edit_problems(
    start: float,
    end: float,
    cut_ranges: list[CutRange],
    caption_template: str,
    duration: float,
    segments: Sequence[SourceSpan] = (),
) -> list[str]:
    """Return what is wrong with a clip from start to end seconds of a source
    of duration seconds (0 if not known yet), with cut_ranges,
    caption_template and segments (none: one from start to end); an empty
    list for a valid clip."""
    problems = []
    if end <= start:
        problems.append(f"end ({end:g}) must be after start ({start:g})")
    if duration > 0 and end > duration:
        problems.append(f"end ({end:g}) is after the end of the video ({duration:g})")
    for cut_start, cut_end in cut_ranges:
        if not start <= cut_start < cut_end <= end:
            problems.append(
                f"cut range [{cut_start:g}, {cut_end:g}] is not a range inside "
                f"the clip [{start:g}, {end:g}]"
            )
    fps = config.settings.render.fps
    sections = segments or [(start, end)]
    if not problems and not played_spans(start, end, sections, cut_ranges, fps):
        problems.append("the cut ranges leave nothing of the clip")
    if caption_template not in load_templates():
        known = ", ".join(load_templates())
        problems.append(
            f"unknown caption template {caption_template!r} (known: {known})"
        )
    return problems


def apply_patch(
    session: Session, row: ClipRow, patch: ClipPatch, duration: float
) -> None:
    """Apply patch to the clip row, in session, and commit.

    The fields that patch sets (not None) replace the row's; cut ranges and
    zoom keyframes are stored in time order, and scenes with their edges
    exactly on each other's and the clip's (scenes.snap_scenes). A new start
    or end moves the clip's segments (timeline.respan) and its video track
    with them, and its stored scenes' outer edges (scenes.fit_scenes) unless
    patch sets the scenes. Raises
    ClipEditError, and changes nothing, if the patched clip is not valid
    (edit_problems for a source of duration seconds, or a segment left
    empty).
    """
    changes = patch.model_dump(exclude_none=True)
    if "cut_ranges" in changes:
        changes["cut_ranges"] = sorted(patch.cut_ranges or [])
    if patch.zoom_keyframes is not None:
        changes["zoom_keyframes"] = sorted(patch.zoom_keyframes, key=lambda k: k.t)
    clip = row.to_model()
    start = changes.pop("start", clip.start)
    end = changes.pop("end", clip.end)
    segments, problems = clip.segments, []
    if (start, end) != (clip.start, clip.end) and start < end:
        try:
            segments = respan(clip.segments, start, end)
        except ValueError as exc:
            problems.append(str(exc))
    problems += edit_problems(
        start,
        end,
        changes.get("cut_ranges", row.cut_ranges),
        changes.get("caption_template", row.caption_template),
        duration,
        segments,
    )
    if patch.caption_style is not None:
        problems += style_problems(patch.caption_style)
    if patch.scene_reframes is not None:
        problems += scene_problems(patch.scene_reframes, start, end)
        changes["scene_reframes"] = snap_scenes(patch.scene_reframes, start, end)
    elif (start, end) != (clip.start, clip.end) and clip.scene_reframes:
        changes["scene_reframes"] = fit_scenes(clip.scene_reframes, start, end)
    if problems:
        raise ClipEditError("; ".join(problems))
    if (start, end) != (clip.start, clip.end):
        changes["segments"] = segments
        changes["tracks"] = with_segments(clip.tracks, segments)
    for name in ("caption_overrides", "caption_style", "framing", "transitions"):
        if name in changes:
            changes[name] = getattr(patch, name)
    for name, value in changes.items():
        setattr(row, name, value)
    session.add(row)
    session.commit()
    session.refresh(row)


def section_problems(
    segments: Sequence[SourceSpan], duration: float, fps: int
) -> list[str]:
    """Return what is wrong with segments as a clip's sections in a source of
    duration seconds (0 if not known): each must lie in the source and last
    a frame at fps at least, and no two may overlap."""
    problems = []
    for index, (start, end) in enumerate(segments):
        if end - start < 1 / fps:
            problems.append(f"section {index} is shorter than a frame")
        if duration > 0 and end > duration:
            problems.append(
                f"section {index} ends after the end of the video ({duration:g})"
            )
    for (_, before_end), (after_start, after_end) in pairwise(sorted(segments)):
        if after_start < before_end:
            problems.append(
                f"sections overlap at [{after_start:g}, {min(before_end, after_end):g}]"
            )
    return problems


def trim_section(
    segments: Sequence[SourceSpan],
    index: int,
    start: float,
    end: float,
    duration: float,
) -> list[SourceSpan]:
    """Return segments with section index trimmed or extended to start..end
    seconds, clamped to the source (0..duration, if known) and to the
    sections next to it in the source."""
    _section(segments, index)
    old_start, old_end = segments[index]
    others = [span for n, span in enumerate(segments) if n != index]
    low = max([0.0, *(e for s, e in others if e <= old_start)])
    top = duration if duration > 0 else math.inf
    high = min([top, *(s for s, e in others if s >= old_end)])
    moved = list(segments)
    moved[index] = (max(start, low), min(end, high))
    if moved[index][1] <= moved[index][0]:
        raise ClipEditError(
            f"[{start:g}, {end:g}] leaves nothing of section {index} between "
            f"{low:g} and {high:g}"
        )
    return moved


def add_section(
    segments: Sequence[SourceSpan],
    start: float,
    end: float,
    duration: float,
    index: int | None = None,
) -> list[SourceSpan]:
    """Return segments with start..end seconds of the source, clamped to it
    (0..duration, if known), added as a section that plays at index (None:
    last). Raises ClipEditError if it overlaps a section or the source."""
    if index is not None and index > len(segments):
        raise ClipEditError(
            f"index {index} is after the clip's {len(segments)} sections"
        )
    if duration > 0:
        end = min(end, duration)
    if end <= start:
        raise ClipEditError(f"[{start:g}, {end:g}] is not inside the video")
    for n, (other_start, other_end) in enumerate(segments):
        if start < other_end and other_start < end:
            raise ClipEditError(f"[{start:g}, {end:g}] overlaps section {n}")
    added = list(segments)
    added.insert(len(segments) if index is None else index, (start, end))
    return added


def split_section(segments: Sequence[SourceSpan], at: float) -> list[SourceSpan]:
    """Return segments with the section that plays at seconds of the source
    split into two sections at that time, which play one after the other."""
    for index, (start, end) in enumerate(segments):
        if start < at < end:
            split = list(segments)
            split[index : index + 1] = [(start, at), (at, end)]
            return split
    raise ClipEditError(f"no section plays {at:g} s of the video (inside it)")


def delete_section(segments: Sequence[SourceSpan], index: int) -> list[SourceSpan]:
    """Return segments without section index; a clip keeps one at least."""
    _section(segments, index)
    if len(segments) == 1:
        raise ClipEditError("the clip's only section cannot be deleted")
    return [span for n, span in enumerate(segments) if n != index]


def reorder_sections(
    segments: Sequence[SourceSpan], order: Sequence[int]
) -> list[SourceSpan]:
    """Return segments in order, the sections' current indices in their new
    play order, each index once."""
    if sorted(order) != list(range(len(segments))):
        raise ClipEditError(
            f"order {list(order)} is not each of 0..{len(segments) - 1} once"
        )
    return [segments[index] for index in order]


def apply_sections(
    session: Session, row: ClipRow, segments: Sequence[SourceSpan], duration: float
) -> None:
    """Give the clip row segments as its sections, in session, and commit.

    The video track plays them (timeline.with_segments), the cut ranges keep
    their parts inside them (fit_cuts) and the scenes are fitted to their
    new span (scenes.fit_scenes). Raises ClipEditError, and changes
    nothing, if the sections are not valid in a source of duration seconds
    (section_problems) or the cuts leave nothing of them.
    """
    clip, fps = row.to_model(), config.settings.render.fps
    problems = section_problems(segments, duration, fps)
    cuts = fit_cuts(clip.cut_ranges, segments)
    start = min(span_start for span_start, _ in segments)
    end = max(span_end for _, span_end in segments)
    if not problems and not played_spans(start, end, segments, cuts, fps):
        problems.append("the cut ranges leave nothing of the clip")
    if problems:
        raise ClipEditError("; ".join(problems))
    row.segments = list(segments)
    row.tracks = with_segments(clip.tracks, segments)
    row.cut_ranges = cuts
    if (start, end) != (clip.start, clip.end) and clip.scene_reframes:
        row.scene_reframes = fit_scenes(clip.scene_reframes, start, end)
    session.add(row)
    session.commit()
    session.refresh(row)


def _section(segments: Sequence[SourceSpan], index: int) -> None:
    """Raise SectionNotFound unless segments has a section index."""
    if not 0 <= index < len(segments):
        raise SectionNotFound(f"the clip has no section {index}")
