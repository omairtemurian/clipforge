"""The thresholds of the auto zoom-out moments (TASK-198,
pipeline/layout_auto), set in config.yaml under zoom_out.

The values are those of the "balanced" intensity; intensity_factors scale
them for the others (layout_auto.zoom_params): a factor above 1 zooms out
more often (a larger share, bigger faces count as a wide shot, a shorter
lost subject, less spread motion), below 1 less often.
"""

from pydantic import BaseModel, Field, PositiveFloat


class ZoomOutSettings(BaseModel):
    # The most of a clip's length that may be zoomed out.
    max_share: float = Field(default=0.4, ge=0, le=1)
    # The shortest zoomed-out (and the shortest fill) segment, in seconds.
    min_segment_s: PositiveFloat = 2.5
    # The zoom between fill and a zoomed-out layout, in seconds (not at a
    # scene cut, which stays a hard cut).
    transition_s: float = Field(default=0.3, ge=0, le=2)
    # A wide shot: the largest face is less tall than this share of the frame.
    wide_face_height: float = Field(default=0.12, ge=0, le=1)
    # The subject is lost when no face or person is seen for longer than this.
    lost_s: PositiveFloat = 1.0
    # Wide action: at least this share of the frame's columns move.
    motion_spread: float = Field(default=0.5, ge=0, le=1)
    # Hysteresis: the share of a window_s window of samples that want a zoom
    # out to start one (enter), and at or below which it ends (exit).
    enter: float = Field(default=0.7, ge=0, le=1)
    exit: float = Field(default=0.3, ge=0, le=1)
    window_s: PositiveFloat = 1.0
    intensity_factors: dict[str, PositiveFloat] = {
        "subtle": 0.5,
        "balanced": 1.0,
        "frequent": 1.5,
    }
