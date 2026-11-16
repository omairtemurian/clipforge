"""Flashes of a video (SPEC-v3 4.3): single bright frames, found from the
luma of each sampled frame (features/color).

A frame flashes when it is near-white (luma at least WHITE_LUMA and
saturation below WHITE_SATURATION) or a luma spike: SPIKE_LUMA brighter
than the median of the NEIGHBOURS frames on each side of it. Runs of such
frames make one flash if they last at most MAX_FLASH_FRAMES; longer runs
are a bright shot, not a flash.
"""

from collections.abc import Sequence

import numpy as np
from pydantic import BaseModel, Field

from clipforge.models import UnitInterval
from clipforge.proedit.features.color import FrameColor, runs

WHITE_LUMA = 0.9
WHITE_SATURATION = 0.1
SPIKE_LUMA = 0.2
NEIGHBOURS = 6
MAX_FLASH_FRAMES = 6
DECIMALS = 4


class Flash(BaseModel):
    """A flash from start to end seconds; peak is its highest frame luma and
    white tells whether a frame of it is near-white."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    peak: UnitInterval
    white: bool


class FlashStats(BaseModel):
    """The flashes of a video and how many come per minute."""

    flashes: list[Flash]
    per_minute: float = Field(ge=0)


def flash_frames(frames: Sequence[FrameColor]) -> list[bool]:
    """Return for each frame whether it flashes (module doc), before the
    MAX_FLASH_FRAMES limit."""
    lumas = np.array([frame.luma for frame in frames], dtype=np.float64)
    flags = []
    for index, frame in enumerate(frames):
        around = np.concatenate(
            [
                lumas[max(0, index - NEIGHBOURS) : index],
                lumas[index + 1 : index + 1 + NEIGHBOURS],
            ]
        )
        spike = len(around) > 0 and frame.luma - float(np.median(around)) >= SPIKE_LUMA
        flags.append(spike or _white(frame))
    return flags


def detect_flashes(frames: Sequence[FrameColor], fps: float) -> FlashStats:
    """Return the flashes of a video whose frame k (k / fps seconds) has the
    color frames[k]."""
    flashes = []
    for start, end in runs(flash_frames(frames), fps):
        first, last = round(start * fps), round(end * fps)
        if last - first > MAX_FLASH_FRAMES:
            continue
        part = frames[first:last]
        flashes.append(
            Flash(
                start=start,
                end=end,
                peak=max(frame.luma for frame in part),
                white=any(_white(frame) for frame in part),
            )
        )
    minutes = len(frames) / fps / 60 if frames else 0
    per_minute = round(len(flashes) / minutes, DECIMALS) if minutes else 0.0
    return FlashStats(flashes=flashes, per_minute=per_minute)


def _white(frame: FrameColor) -> bool:
    """Return whether frame is near-white."""
    return frame.luma >= WHITE_LUMA and frame.saturation < WHITE_SATURATION
