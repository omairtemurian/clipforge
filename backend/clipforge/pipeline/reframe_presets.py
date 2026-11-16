"""Genre reframing presets (SPEC-v2 3.3): the layout and the tracking
parameters reframe uses for a kind of video.

A preset sets, on top of the defaults of pipeline/reframe and
pipeline/tracking, the layout, the split share and the camera motion
(pipeline/camera_motion) that picking it sets (the project's camera motion
setting, if given, wins):

- podcast-2: two people talking; the split layout when both faces persist
  in 40% of the samples (instead of 60%), the window calmly follows who
  speaks;
- standup: one performer who paces a stage; always fill, never split, with
  fast camera motion to keep up;
- gaming: a screen recording or screenshare; always fit (the whole frame
  over a blurred copy), so no crop follows anything;
- vlog: handheld video of one person or thing; always fill, calm camera
  motion against shake, and a moving object is followed in shots without
  a face.

Without a preset, reframe uses DEFAULT (calm).
"""

from typing import NamedTuple

from clipforge.models import CameraMotion, Layout, ReframePreset, ReframePresetInfo
from clipforge.pipeline.camera_motion import MOTIONS, Motion


class ReframeParams(NamedTuple):
    """What a preset changes in reframe: layout is the layout of every clip
    (None: choose it by the faces); split_share the share of the samples
    that need two faces to split; camera_motion how the windows move
    (tracking.follow); objects whether a moving object is followed in shots
    without a face."""

    layout: Layout | None
    split_share: float
    camera_motion: CameraMotion
    objects: bool

    @property
    def motion(self) -> Motion:
        """Return the dead-zone, pan speed and hold of camera_motion."""
        return MOTIONS[self.camera_motion]


DEFAULT = ReframeParams(
    layout=None, split_share=0.6, camera_motion="calm", objects=True
)

# Why share 1: more than all the samples cannot have two faces, so no split.
_NEVER_SPLIT = 1.0

PARAMS: dict[ReframePreset, ReframeParams] = {
    "podcast-2": ReframeParams(None, 0.4, "calm", False),
    "standup": ReframeParams("fill", _NEVER_SPLIT, "fast", False),
    "gaming": ReframeParams("fit", _NEVER_SPLIT, "calm", False),
    "vlog": ReframeParams("fill", _NEVER_SPLIT, "calm", True),
}

LABELS: dict[ReframePreset, tuple[str, str]] = {
    "podcast-2": ("Podcast, two people", "Split screen when both people are seen."),
    "standup": ("Stand-up", "One performer, followed closely across the stage."),
    "gaming": ("Gaming / screenshare", "The whole screen over a blurred copy."),
    "vlog": ("Vlog", "Steady, slower follow of one person or object."),
}


def params_for(
    preset: ReframePreset | None, camera_motion: CameraMotion | None = None
) -> ReframeParams:
    """Return the parameters of preset, or DEFAULT for None, with
    camera_motion instead of the preset's if it is given."""
    params = DEFAULT if preset is None else PARAMS[preset]
    if camera_motion is None:
        return params
    return params._replace(camera_motion=camera_motion)


def preset_infos() -> list[ReframePresetInfo]:
    """Return every preset with its label and parameters, in table order."""
    infos = []
    for name, params in PARAMS.items():
        label, description = LABELS[name]
        infos.append(
            ReframePresetInfo(
                name=name,
                label=label,
                description=description,
                layout=params.layout,
                split_share=params.split_share,
                camera_motion=params.camera_motion,
                objects=params.objects,
            )
        )
    return infos
