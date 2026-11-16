"""Signals step (SPEC 6.3): the events in a job's timeframe -> signals.json.

The audio, audio.wav, is analyzed in one pass (pipeline/audio_analysis):
YAMNet scores the Laughter, Applause, Cheering and Music classes
(pipeline/audio_events), whose per-second scores go to audio_events.json, and
librosa measures the RMS envelope. YAMNet frame i reads [0.48 i, 0.48 i + 0.96]
s of the timeframe and stands for the 0.48 s in its middle,
[0.48 i + 0.24, 0.48 i + 0.72], so that the frames tile the timeframe. Frames
that score above 0.3 are merged into laugh, applause, cheer and music events
(pipeline/signal_merge), and an event's intensity is its mean score, scaled by
how much louder it is than the median level of the 30 s around it. Silences
and energy peaks come from the envelope (pipeline/level_events): an energy
peak's intensity is that loudness scale alone, and a silence's is 1. Scene
cuts come from the video, source.mp4 (pipeline/scene_cuts); a cut is an
instant (start = end) of intensity 1.
"""

import logging
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import get_args

import numpy as np
import numpy.typing as npt

from clipforge.config import Settings
from clipforge.models import (
    AudioEventList,
    AudioEventTrack,
    SignalEvent,
    SignalKind,
    SignalList,
)
from clipforge.pipeline import yamnet
from clipforge.pipeline.audio_analysis import analyze_audio
from clipforge.pipeline.audio_events import EVENT_CLASSES, audio_track
from clipforge.pipeline.level_events import energy_peaks, silences
from clipforge.pipeline.loudness import Envelope
from clipforge.pipeline.scene_cuts import detect_scene_cuts
from clipforge.pipeline.signal_merge import ScoredSpan, intensity, merge_active_frames
from clipforge.pipeline.step import (
    AUDIO,
    AUDIO_EVENTS,
    SIGNALS,
    SOURCE,
    StepError,
    StepSettings,
    is_done,
    load_meta,
    write_json,
)

# The YAMNet class (its display name in the class map) of each audio event.
CLASSES = EVENT_CLASSES
ACTIVE_SCORE = 0.3
BASELINE_WINDOW_S = 30.0
HOP_S = yamnet.HOP_SAMPLES / yamnet.SAMPLE_RATE
# Times and intensities are rounded to milliseconds / 3 decimals.
DECIMALS = 3
# The share of the step's progress for the audio; the video takes the rest
# (10 min of 720p30 took 1.1 s for the audio and 5.0 s for the video).
AUDIO_SHARE = 0.2

logger = logging.getLogger(__name__)


def run(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
    """Write the signal events of the job's timeframe to signals.json.

    Reads meta.json, audio.wav and source.mp4, which ingest wrote. The
    events are sorted by start, then kind; their times are source times
    within the timeframe. Skips the work if signals.json exists, unless
    force. Raises StepError if ingest has not run, audio.wav is not 16 kHz
    mono 16-bit PCM, source.mp4 cannot be decoded, or the YAMNet model is
    missing or broken.
    """
    output = job_dir / SIGNALS
    if is_done(output, force=force):
        logger.info("%s exists; skipping signals", output)
        settings.report_progress(1.0)
        return output
    output.unlink(missing_ok=True)

    meta = load_meta(job_dir)
    audio, video = job_dir / AUDIO, job_dir / SOURCE
    for path in (audio, video):
        if not path.is_file():
            raise StepError(f"{path} not found; run the ingest step first")
    start, end = meta.timeframe_start, meta.timeframe_end
    found = analyze_signals(
        audio,
        start,
        end,
        settings.cfg,
        on_progress=lambda done: settings.report_progress(AUDIO_SHARE * done),
    )
    events = found.events
    cuts = detect_scene_cuts(
        video,
        start,
        end,
        on_progress=lambda done: settings.report_progress(
            AUDIO_SHARE + (1 - AUDIO_SHARE) * done
        ),
    )
    events += [flat_event("scene_cut", time, time) for time in cuts]
    events.sort(key=lambda event: (event.start, event.kind))
    write_json(job_dir / AUDIO_EVENTS, AudioEventList(found.tracks))
    write_json(output, SignalList(events))
    counts = Counter(event.kind for event in events)
    logger.info(
        "found %s events in %.1fs-%.1fs",
        ", ".join(f"{counts[kind]} {kind}" for kind in get_args(SignalKind)),
        start,
        end,
    )
    return output


@dataclass(frozen=True)
class AudioSignals:
    """The events of the audio of a timeframe and the per-second scores of its
    audio event classes (one AudioEventTrack per kind in CLASSES)."""

    events: list[SignalEvent]
    tracks: list[AudioEventTrack]


def detect_audio_signals(
    audio: Path,
    start: float,
    end: float,
    cfg: Settings,
    *,
    on_progress: Callable[[float], None] | None = None,
) -> list[SignalEvent]:
    """Return the events that the audio in [start, end] s shows, by start.

    See analyze_signals, which also returns the per-second scores.
    """
    return analyze_signals(audio, start, end, cfg, on_progress=on_progress).events


def analyze_signals(
    audio: Path,
    start: float,
    end: float,
    cfg: Settings,
    *,
    on_progress: Callable[[float], None] | None = None,
) -> AudioSignals:
    """Return what the audio in [start, end] s shows: events and score tracks.

    The events, by start, are the laugh, applause, cheer, music, silence and
    energy-peak events of audio, a 16 kHz mono 16-bit PCM WAV file, in source
    times; the tracks hold the per-second scores of the four YAMNet classes.
    on_progress gets the fraction of the audio done. Raises StepError if
    audio cannot be read or has another format, or the YAMNet model is
    missing or broken or has no class of CLASSES.
    """
    model = yamnet.load_yamnet(cfg)
    kinds = list(CLASSES)
    analysis = analyze_audio(
        audio,
        start,
        end,
        model,
        [model.class_index(CLASSES[kind]) for kind in kinds],
        on_progress=on_progress,
    )
    envelope = analysis.envelope
    events: list[SignalEvent] = []
    tracks: list[AudioEventTrack] = []
    for column, kind in enumerate(kinds):
        frames = frame_spans(analysis.start, analysis.scores[:, column], analysis.end)
        tracks.append(audio_track(kind, frames, analysis.start, analysis.end))
        spans = merge_active_frames(
            frames,
            threshold=ACTIVE_SCORE,
            max_gap=cfg.laugh_merge_gap_s,
            min_duration=cfg.laugh_min_duration_s,
        )
        events += [signal_event(kind, span, envelope) for span in spans]
    peaks = energy_peaks(envelope, analysis.end)
    events += [signal_event("energy_peak", span, envelope) for span in peaks]
    quiet = silences(envelope, analysis.end)
    events += [flat_event("silence", span.start, span.end) for span in quiet]
    events.sort(key=lambda event: (event.start, event.kind))
    return AudioSignals(events, tracks)


def frame_spans(
    start: float, scores: Sequence[float] | npt.NDArray[np.float32], end: float
) -> list[ScoredSpan]:
    """Return the spans that YAMNet frames with scores stand for.

    The frames are those of audio from source time start: frame i stands
    for [start + 0.48 i + 0.24, start + 0.48 i + 0.72], cut at end; a frame
    whose span lies past end is left out.
    """
    spans = []
    for index, score in enumerate(scores):
        span_start = start + index * HOP_S + HOP_S / 2
        span_end = min(span_start + HOP_S, end)
        if span_end > span_start:
            spans.append(ScoredSpan(span_start, span_end, float(score)))
    return spans


def signal_event(kind: SignalKind, span: ScoredSpan, envelope: Envelope) -> SignalEvent:
    """Return the event of kind for span, with its intensity (SPEC 6.3).

    The intensity compares the level of the span in envelope with the
    rolling median level of the BASELINE_WINDOW_S around its middle; it is
    0 if the envelope has no frame there.
    """
    level = envelope.level(span.start, span.end)
    baseline = envelope.baseline((span.start + span.end) / 2, BASELINE_WINDOW_S)
    rating = 0.0
    if level is not None and baseline is not None:
        rating = intensity(span.score, level, baseline)
    return SignalEvent(
        kind=kind,
        start=round(span.start, DECIMALS),
        end=round(span.end, DECIMALS),
        intensity=round(rating, DECIMALS),
    )


def flat_event(kind: SignalKind, start: float, end: float) -> SignalEvent:
    """Return the event of kind in [start, end] s, with intensity 1."""
    return SignalEvent(
        kind=kind,
        start=round(start, DECIMALS),
        end=round(end, DECIMALS),
        intensity=1.0,
    )
