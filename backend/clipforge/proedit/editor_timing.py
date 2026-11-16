"""What the Pro Edit editor snaps a dragged item to (SPEC-v3 3.1, 3.8), in
seconds of the rendered clip: the render's frame rate and the clip's length
(timeline.clip_length), its words as the captions play them (the
transcript with the clip's caption overrides and marks, retimed by its cuts
and segments: pipeline/sections.played_words, as proedit/signals does) and
the beats of the music beds of its current plan (beats.music_grid of each
bed's file from the bed's music offset, audio/music_bed.bed_offsets, kept
within the bed).

Nothing heavy runs: no face search or motion (unlike signals.build_signals).
A music file's grid is read once per file version (cached).
"""

from functools import cache
from pathlib import Path

from sqlmodel import Session

from clipforge import assets
from clipforge.models import Clip, ProEditPlan, ProEditTiming, ProEditWord, Transcript
from clipforge.pipeline.caption_lines import clip_words
from clipforge.pipeline.sections import played_words
from clipforge.pipeline.step import TRANSCRIPT, StepError, load_json
from clipforge.proedit.audio.music_bed import bed_offsets, music_beds
from clipforge.proedit.audio.sounds import find_sound
from clipforge.proedit.beats import MusicGrid, beats_in_clip, music_grid
from clipforge.proedit.edl import EdlValidationError, TypedEdlItem, parse_item
from clipforge.timeline import clip_length

DECIMALS = 3


def editor_timing(
    session: Session, work: Path, clip: Clip, plan: ProEditPlan | None, fps: int
) -> ProEditTiming:
    """Return the timing of clip (its project's job directory is work) at
    fps, with the beats of plan's music beds (none without a plan). Raises
    StepError if the job's transcript is missing or not valid."""
    transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    duration = clip_length(clip, fps)
    marks = clip.caption_style.word_marks or []
    words = clip_words(transcript, clip.start, clip.end, clip.caption_overrides, marks)
    return ProEditTiming(
        fps=fps,
        duration=round(duration, DECIMALS),
        words=[
            ProEditWord(text=w.text.strip(), start=w.start / 1000, end=w.end / 1000)
            for w in played_words(words, clip, fps)
        ],
        beats=[] if plan is None else plan_beats(session, plan, duration),
    )


def plan_beats(session: Session, plan: ProEditPlan, duration: float) -> list[float]:
    """Return the beats (seconds of the clip, sorted, each once) of the
    music beds of plan whose file is found and decodes; each bed's beats
    lie within it."""
    library = {str(a.id): Path(a.path) for a in assets.list_assets(session) if a.path}
    beds = music_beds(_typed(plan))
    offsets = bed_offsets(beds)
    beats: set[float] = set()
    for bed in beds:
        path = find_sound(bed.params.asset, library)
        grid = _grid(path)
        if grid is None:
            continue
        times = beats_in_clip(grid.beats, bed.t_start, duration, offsets[bed.id])
        beats.update(t for t in times if bed.t_start <= t < bed.t_end)
    return sorted(beats)


def _typed(plan: ProEditPlan) -> list[TypedEdlItem]:
    typed: list[TypedEdlItem] = []
    for item in plan.items:
        try:
            typed.append(parse_item(item))
        except EdlValidationError:
            continue
    return typed


def _grid(path: Path | None) -> MusicGrid | None:
    """The beat grid of path; None if it is missing or does not decode."""
    if path is None or not path.is_file():
        return None
    try:
        return _cached_grid(str(path), path.stat().st_mtime_ns)
    except StepError:
        return None


@cache
def _cached_grid(path: str, _mtime_ns: int) -> MusicGrid:
    return music_grid(Path(path))
