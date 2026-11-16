"""Auto zoom (TASK-23): punch-ins that magnify a clip's frames for a moment.

A new clip gets zoom keyframes (models.ZoomKeyframe) at three kinds of
moments, its triggers, each with its own scale:

- the first word of each run of the clip's emphasis_words (EMPHASIS_SCALE);
- each new sentence after a pause that auto cut takes out (auto_cut.auto_cuts,
  with the project's min pause, whether auto_cut is on or not): the end of
  the cut, where the next word is about to start (SENTENCE_SCALE);
- the start of each laugh or energy_peak event (signals.json) of the clip
  (REACTION_SCALE).

Each punch-in ramps from scale 1 to its scale over RAMP_IN_MS so that it is
in full at its trigger (a punch on a jump cut happens on the cut), holds it
for HOLD_MS (less, down to MIN_HOLD_MS, so it ends by the clip's end) and
eases back to 1 over RAMP_OUT_MS. The triggers are taken by priority, the
larger scale first (emphasis, then reactions, then sentences), each in time
order, skipping those less than MIN_GAP_MS from a punch-in already taken,
before RAMP_IN_MS into the clip or too close to its end for MIN_HOLD_MS. So
a punch-in ends before the next one starts, and the keyframes are in time
order, 4 per punch-in.

The render (pipeline/zoom_graph) zooms the framed clip about its subject.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path

from clipforge.models import (
    ProcessingSettings,
    SignalEvent,
    Transcript,
    ZoomKeyframe,
)
from clipforge.pipeline.auto_cut import auto_cuts
from clipforge.pipeline.caption_lines import clip_words, mark_emphasis, to_ms
from clipforge.pipeline.polish import load_polish_inputs

EMPHASIS_SCALE = 1.15
REACTION_SCALE = 1.13
SENTENCE_SCALE = 1.12
REACTION_KINDS = frozenset({"laugh", "energy_peak"})
RAMP_IN_MS = 200
HOLD_MS = 2000
MIN_HOLD_MS = 1500
RAMP_OUT_MS = 500
MIN_GAP_MS = 3000

# A moment to punch in at: its time in milliseconds of the source and scale.
Trigger = tuple[int, float]


def zoom_triggers(
    transcript: Transcript,
    events: Iterable[SignalEvent],
    emphasis_words: Sequence[str],
    start: float,
    end: float,
    min_pause_s: float,
) -> list[Trigger]:
    """Return the triggers of the clip from start to end (module docstring),
    by time, the larger scale first at the same time."""
    first, last = to_ms(start), to_ms(end)
    triggers: list[Trigger] = []
    words = mark_emphasis(clip_words(transcript, start, end), emphasis_words)
    previous = False
    for word in words:
        if word.emphasis and not previous:
            triggers.append((first + word.start, EMPHASIS_SCALE))
        previous = word.emphasis
    for _, cut_end in auto_cuts(transcript, events, start, end, min_pause_s):
        triggers.append((to_ms(cut_end), SENTENCE_SCALE))
    for event in events:
        if event.kind in REACTION_KINDS and first <= to_ms(event.start) < last:
            triggers.append((to_ms(event.start), REACTION_SCALE))
    return sorted(triggers, key=lambda trigger: (trigger[0], -trigger[1]))


def punch_ins(
    triggers: Iterable[Trigger], start: float, end: float
) -> list[ZoomKeyframe]:
    """Return the zoom keyframes of the punch-ins at triggers, in time order,
    of a clip from start to end seconds (module docstring)."""
    first, last = to_ms(start), to_ms(end)
    taken: list[Trigger] = []
    for time, scale in sorted(triggers, key=lambda trigger: (-trigger[1], trigger[0])):
        fits = time - RAMP_IN_MS >= first and last - RAMP_OUT_MS - time >= MIN_HOLD_MS
        if fits and all(abs(time - other) >= MIN_GAP_MS for other, _ in taken):
            taken.append((time, scale))
    keyframes: list[ZoomKeyframe] = []
    for time, scale in sorted(taken):
        held = time + min(HOLD_MS, last - RAMP_OUT_MS - time)
        keyframes += [
            ZoomKeyframe(t=(time - RAMP_IN_MS) / 1000, scale=1.0),
            ZoomKeyframe(t=time / 1000, scale=scale),
            ZoomKeyframe(t=held / 1000, scale=scale),
            ZoomKeyframe(t=(held + RAMP_OUT_MS) / 1000, scale=1.0),
        ]
    return keyframes


def auto_zoom_keyframes(
    transcript: Transcript,
    events: Sequence[SignalEvent],
    emphasis_words: Sequence[str],
    start: float,
    end: float,
    min_pause_s: float,
) -> list[ZoomKeyframe]:
    """Return the zoom keyframes of the clip from start to end: its
    punch-ins at its triggers (module docstring)."""
    triggers = zoom_triggers(
        transcript, events, emphasis_words, start, end, min_pause_s
    )
    return punch_ins(triggers, start, end)


def new_clip_zooms(
    job_dir: Path,
    clips: Iterable[tuple[float, float, Sequence[str]]],
    processing: ProcessingSettings,
) -> list[list[ZoomKeyframe]]:
    """Return the zoom keyframes of new clips (start, end, emphasis_words),
    in order (auto_zoom_keyframes), with processing.auto_zoom on; none
    with it off.

    job_dir's transcript.json and signals.json are read only with auto_zoom
    on (and clips); raises StepError if one of them is missing or not valid.
    """
    clips = list(clips)
    if not clips or not processing.auto_zoom:
        return [[] for _ in clips]
    transcript, events = load_polish_inputs(job_dir)
    pause = processing.auto_cut_min_pause_s
    return [
        auto_zoom_keyframes(transcript, events, words, start, end, pause)
        for start, end, words in clips
    ]
