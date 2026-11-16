"""The structure of a style reference (SPEC-v3 4.3 structure), from its
video and audio features.

Effects are the cuts, zoom starts, shake starts, flash starts, glitch
(RGB-split and spike) starts and SFX onsets. The time to the first effect
is when the earliest one happens (None without effects); the effect
density counts them in each DENSITY_WINDOW_S window (the last one may be
shorter).

The hook is the opening of the video up to its first change of pace: the
first cut or the first music drop, whichever comes first (the whole video
without either).

The ending is a "loop" when the last frame looks like the first one (the
frame descriptors of features/cuts are less than CUT_DISTANCE apart, so the
cut detector would not see a cut from the end back to the start), else a
"hard_cut".
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from clipforge.ffmpeg import FFmpegError, MediaInfo, probe_media
from clipforge.pipeline.frame_stream import stream_frames
from clipforge.pipeline.step import StepError
from clipforge.proedit.features.color import Frame
from clipforge.proedit.features.cuts import CUT_DISTANCE, distance, frame_descriptor
from clipforge.proedit.features.video import ANALYSIS_WIDTH
from clipforge.proedit.style.analyze_audio import AudioFeatures
from clipforge.proedit.style.analyze_video import ReferenceVideoFeatures

DENSITY_WINDOW_S = 5.0
END_FRAMES = 3
DECIMALS = 4

EffectKind = Literal["cut", "zoom", "shake", "flash", "glitch", "sfx"]
Ending = Literal["loop", "hard_cut"]


class Effect(BaseModel):
    """An effect of the reference: what it is and when it starts."""

    time: float = Field(ge=0)
    kind: EffectKind


class StructureFeatures(BaseModel):
    """The structure of a reference (module doc)."""

    time_to_first_effect: float | None = None
    first_effect: EffectKind | None = None
    hook_s: float = Field(ge=0)
    density_window_s: float = Field(default=DENSITY_WINDOW_S, gt=0)
    effect_density: list[int]
    ending: Ending
    ending_distance: float = Field(ge=0)


def analyze_structure(
    path: Path, video: ReferenceVideoFeatures, audio: AudioFeatures | None
) -> StructureFeatures:
    """Return the structure of the reference at path from its video and
    audio features (module doc). Raises StepError if it cannot be decoded."""
    try:
        info = probe_media(path)
        first, last = end_frames(path, info)
    except FFmpegError as exc:
        raise StepError(f"cannot read the frames of {path}: {exc}") from exc
    effects = effects_of(video, audio)
    duration = video.video.duration
    gap = round(distance(frame_descriptor(first), frame_descriptor(last)), DECIMALS)
    return StructureFeatures(
        time_to_first_effect=effects[0].time if effects else None,
        first_effect=effects[0].kind if effects else None,
        hook_s=hook_length(video, audio),
        effect_density=density(effects, duration),
        ending="loop" if gap < CUT_DISTANCE else "hard_cut",
        ending_distance=gap,
    )


def effects_of(
    video: ReferenceVideoFeatures, audio: AudioFeatures | None
) -> list[Effect]:
    """Return the effects of a reference (module doc), in time order."""
    found = video.video
    effects = [Effect(time=t, kind="cut") for t in found.cuts.cuts]
    effects += [Effect(time=z.start, kind="zoom") for z in found.motion.zooms]
    effects += [Effect(time=s.start, kind="shake") for s in found.motion.shakes]
    effects += [Effect(time=f.start, kind="flash") for f in found.flashes.flashes]
    glitches = video.glitches.splits + video.glitches.spikes
    effects += [Effect(time=g.start, kind="glitch") for g in glitches]
    if audio is not None:
        effects += [Effect(time=t, kind="sfx") for t in audio.sfx_onsets]
    return sorted(effects, key=lambda effect: effect.time)


def hook_length(video: ReferenceVideoFeatures, audio: AudioFeatures | None) -> float:
    """Return the length of the hook (module doc), in seconds."""
    changes = video.video.cuts.cuts[:1] + (audio.drops[:1] if audio else [])
    return round(min(changes), DECIMALS) if changes else video.video.duration


def density(effects: list[Effect], duration: float) -> list[int]:
    """Return how many effects start in each DENSITY_WINDOW_S window of a
    video of duration seconds."""
    windows = max(1, -int(-duration // DENSITY_WINDOW_S))
    counts = [0] * windows
    for effect in effects:
        counts[min(int(effect.time // DENSITY_WINDOW_S), windows - 1)] += 1
    return counts


def end_frames(path: Path, info: MediaInfo) -> tuple[Frame, Frame]:
    """Return the first and the last frame of the video at path, at the
    analysis width. Raises FFmpegError if they cannot be decoded."""
    width = ANALYSIS_WIDTH
    height = max(2, round(info.height * width / max(info.width, 1) / 2) * 2)
    fps = max(1, round(info.fps))
    first = next(stream_frames(path, 0.0, 1, (width, height), fps), None)
    start = max(0.0, info.duration - END_FRAMES / fps)
    tail = list(stream_frames(path, start, END_FRAMES, (width, height), fps))
    if first is None or not tail:
        raise FFmpegError(f"no frames decoded from {path}")
    return first, tail[-1]
