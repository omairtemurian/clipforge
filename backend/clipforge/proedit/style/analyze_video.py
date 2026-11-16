"""The video features of a style reference (SPEC-v3 4.3): cut rhythm, zooms
and shakes, look, flashes and glitches, as numbers.

One decode pass at the analysis size runs the shared extractors
(features/video.measure_video: cuts, motion, color, flashes) and, on the
same frames, the vignette estimate (features/look), the RGB-split test
(features/glitches, shifts of up to SPLIT_MAX_SHIFT px) and the
frame-difference spikes (features/spikes). Grain needs the frame's own
pixels (scaling smooths noise away), so a second pass reads GRAIN_FPS
frames a second at the video's own size. The vignette and grain of the
video are the medians over its frames.

The beat grid comes from the reference's own audio (beats.music_grid); the
share of cuts and of zoom starts on a beat counts those within one frame of
one (SPEC-v3 9.6). Without an audio stream or with too few beats for a
tempo, bpm and the shares are None.
"""

import math
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field

from clipforge.ffmpeg import FFmpegError, MediaInfo, probe_media
from clipforge.models import UnitInterval
from clipforge.pipeline.frame_stream import stream_frames
from clipforge.pipeline.step import StepError
from clipforge.proedit.beats import MusicGrid, music_grid
from clipforge.proedit.features.color import Frame
from clipforge.proedit.features.cuts import on_beat_share
from clipforge.proedit.features.glitches import channel_offset
from clipforge.proedit.features.look import grain_sigma, vignette_strength
from clipforge.proedit.features.motion import Grey, ShakeSpan, ZoomEvent
from clipforge.proedit.features.spikes import GlitchStats, SpikeFinder, glitch_stats
from clipforge.proedit.features.video import VideoFeatures, measure_video

GRAIN_FPS = 1
SPLIT_MAX_SHIFT = 12
DECIMALS = 4


class Rhythm(BaseModel):
    """The cut rhythm: cuts in each second (the cuts-per-second curve), cuts
    per minute, mean and median shot length (seconds), the tempo of the
    reference's audio and the shares (0..1) of cuts and zoom starts on one
    of its beats."""

    cuts_per_second: list[int]
    cuts_per_minute: float = Field(ge=0)
    mean_shot_s: float = Field(ge=0)
    median_shot_s: float = Field(ge=0)
    bpm: float | None = None
    cuts_on_beat: UnitInterval | None = None
    zooms_on_beat: UnitInterval | None = None


class EventSummary(BaseModel):
    """How many events of a kind a video has, per minute, and their median
    amplitude and duration (seconds); None without events."""

    count: int = Field(ge=0)
    per_minute: float = Field(ge=0)
    amplitude: float | None = None
    duration_s: float | None = None


class MotionSummary(BaseModel):
    """Zoom punches, zoom ramps (amplitude: how much bigger or smaller the
    picture got, 0.2 = 20 %) and shakes (amplitude: the largest jolt in
    frame widths)."""

    punches: EventSummary
    ramps: EventSummary
    shakes: EventSummary


class Look(BaseModel):
    """The vignette strength (0..1, render/grade.py's scale) and the luma
    grain level (0..1) of a video: medians over its frames."""

    vignette: UnitInterval
    grain: UnitInterval


class ReferenceVideoFeatures(BaseModel):
    """The video features of a reference: what the shared extractors
    measured and the summaries made of it."""

    video: VideoFeatures
    rhythm: Rhythm
    motion: MotionSummary
    look: Look
    glitches: GlitchStats


class _Frames:
    """What the decode pass collects per frame next to measure_video."""

    def __init__(self) -> None:
        self.vignettes: list[float] = []
        self.split: list[bool] = []
        self.spikes = SpikeFinder()

    def add(self, rgb: Frame, grey: Grey) -> None:
        """Measure one frame (module doc)."""
        vignette = vignette_strength(rgb)
        if vignette is not None:
            self.vignettes.append(vignette)
        self.split.append(channel_offset(rgb, SPLIT_MAX_SHIFT).is_split)
        self.spikes.add(grey)


def analyze_video(path: Path) -> ReferenceVideoFeatures:
    """Return the video features of the reference at path (module doc).

    Raises StepError if the video or its audio cannot be read.
    """
    try:
        info = probe_media(path)
    except FFmpegError as exc:
        raise StepError(f"cannot read {path}: {exc}") from exc
    frames = _Frames()
    video = measure_video(path, on_frame=frames.add)
    grid = music_grid(path) if info.audio_codec else None
    return ReferenceVideoFeatures(
        video=video,
        rhythm=rhythm_of(video, grid),
        motion=motion_summary(video),
        look=Look(vignette=_median(frames.vignettes) or 0.0, grain=_grain(path, info)),
        glitches=glitch_stats(
            frames.spikes.candidates,
            frames.split,
            _flash_or_cut(video, len(frames.split)),
            video.fps,
        ),
    )


def rhythm_of(video: VideoFeatures, grid: MusicGrid | None) -> Rhythm:
    """Return the cut rhythm of video against the beat grid of its audio
    (None without audio)."""
    cuts = video.cuts
    rhythm = Rhythm(
        cuts_per_second=cuts.cuts_per_second,
        cuts_per_minute=cuts.per_minute,
        mean_shot_s=cuts.mean_shot_s,
        median_shot_s=_median(cuts.shot_lengths) or 0.0,
    )
    if grid is None or grid.bpm is None:
        return rhythm
    frame = 1 / video.fps
    zoom_starts = [zoom.start for zoom in video.motion.zooms]
    return rhythm.model_copy(
        update={
            "bpm": grid.bpm,
            "cuts_on_beat": on_beat_share(cuts.cuts, grid.beats, frame)
            if cuts.cuts
            else None,
            "zooms_on_beat": on_beat_share(zoom_starts, grid.beats, frame)
            if zoom_starts
            else None,
        }
    )


def motion_summary(video: VideoFeatures) -> MotionSummary:
    """Return the zoom punches, ramps and shakes of video, summed up."""
    zooms = video.motion.zooms
    return MotionSummary(
        punches=_summary([z for z in zooms if z.kind == "punch"], video.duration),
        ramps=_summary([z for z in zooms if z.kind == "ramp"], video.duration),
        shakes=_summary(video.motion.shakes, video.duration),
    )


def _summary(
    events: list[ZoomEvent] | list[ShakeSpan], duration: float
) -> EventSummary:
    """Return the count, rate, median amplitude and duration of events."""
    minutes = duration / 60
    amplitudes = [
        max(event.scale, 1 / event.scale) - 1
        if isinstance(event, ZoomEvent)
        else event.amplitude
        for event in events
    ]
    return EventSummary(
        count=len(events),
        per_minute=round(len(events) / minutes, DECIMALS) if minutes else 0.0,
        amplitude=_median(amplitudes),
        duration_s=_median([event.end - event.start for event in events]),
    )


def _grain(path: Path, info: MediaInfo) -> float:
    """Return the median grain of GRAIN_FPS frames a second of path at its
    own size (0 if it has none)."""
    count = math.floor(info.duration * GRAIN_FPS)
    size = (info.width // 2 * 2, info.height // 2 * 2)
    try:
        levels = [
            grain_sigma(rgb) for rgb in stream_frames(path, 0.0, count, size, GRAIN_FPS)
        ]
    except FFmpegError as exc:
        raise StepError(f"cannot measure the grain of {path}: {exc}") from exc
    return _median(levels) or 0.0


def _flash_or_cut(video: VideoFeatures, count: int) -> list[bool]:
    """Return for each of count frames whether it is a flash or starts a shot."""
    flags = [False] * count
    for flash in video.flashes.flashes:
        for index in range(
            round(flash.start * video.fps), round(flash.end * video.fps)
        ):
            flags[min(index, count - 1)] = True
    for cut in video.cuts.cuts:
        flags[min(round(cut * video.fps), count - 1)] = True
    return flags


def _median(values: list[float]) -> float | None:
    """Return the median of values, rounded, or None if there are none."""
    return round(float(np.median(values)), DECIMALS) if values else None
