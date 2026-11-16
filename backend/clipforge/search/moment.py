"""A clip made from a moment that a library search found (SPEC-v2 3.11).

The clip starts where the sentence that holds the moment starts and takes
the sentences after it while they fit in the length asked for. It is a
candidate of the project's current result set, framed and captioned as the
project's settings say, with its title and description from what is said;
it is not rendered (POST /clips/{id}/render does that).
"""

import textwrap

from sqlmodel import Session

from clipforge import config
from clipforge.clip_edit import ClipEditError, section_problems
from clipforge.clips import DEFAULT_LAYOUT
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import CaptionStyle, Scores, Segment, SourceSpan, Transcript
from clipforge.timeline import timeline_of

TITLE_MAX = 70
DESCRIPTION_MAX = 300


def moment_segments(
    transcript: Transcript, at: float, length: float, duration: float
) -> list[Segment]:
    """Return the sentences, in order, that the clip of the moment at seconds
    plays: the one that holds at (or the next one, if at falls in a pause),
    and the ones after it that end within length seconds of its start (and
    within the video's duration seconds, if known). Raises ClipEditError if
    nothing is said at or after at."""
    spoken = [s for s in transcript.segments if s.text.strip() and s.end > s.start]
    first = next((i for i, s in enumerate(spoken) if s.end > at), None)
    if first is None:
        raise ClipEditError(f"nothing is said at or after {at:g} s of the video")
    start = spoken[first].start
    limit = start + length if duration <= 0 else min(start + length, duration)
    chosen = [spoken[first]]
    for segment in spoken[first + 1 :]:
        if segment.end > limit:
            break
        chosen.append(segment)
    return chosen


def clip_from_moment(
    session: Session,
    project: ProjectRow,
    transcript: Transcript,
    at: float,
    length: float,
) -> ClipRow:
    """Add the clip of the moment at seconds of project's video to session's
    database, commit and return it. Raises ClipEditError, and adds nothing,
    if nothing is said there or the clip would not fit in the video."""
    chosen = moment_segments(transcript, at, length, project.duration)
    start = chosen[0].start
    end = min(chosen[-1].end, start + length)
    if project.duration > 0:
        end = min(end, project.duration)
    segments: list[SourceSpan] = [(start, end)]
    problems = section_problems(segments, project.duration, config.settings.render.fps)
    if problems:
        raise ClipEditError("; ".join(problems))
    said = " ".join(" ".join(s.text.split()) for s in chosen)
    processing = project.settings
    row = ClipRow(
        project_id=project.id or 0,
        segments=segments,
        tracks=timeline_of(segments),
        title=textwrap.shorten(said, TITLE_MAX, placeholder="…"),
        hook_text="",
        description=textwrap.shorten(said, DESCRIPTION_MAX, placeholder="…"),
        hashtags=[],
        emphasis_words=[],
        reason=f"Made from the moment at {at:.1f} s found by a library search.",
        scores=Scores(overall=0, hook=0, flow=0, value=0, trend=0, laugh=0, energy=0),
        layout=DEFAULT_LAYOUT,
        caption_template=processing.caption_template,
        caption_style=CaptionStyle(**processing.caption_colors.model_dump()),
        auto_color=processing.auto_color,
        show_captions=processing.captions,
        result_set=project.result_set,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
