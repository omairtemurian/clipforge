"""Manual reframe (SPEC-v2 3.3): the crop keyframes that the crop tool sets
on a scene of a clip (models.SceneReframe) by dragging or resizing its fill
window at the playhead, and where the window is between them.

A keyframe puts the window's center at a point of the source frame at a
time inside the scene (models.CropPoint). Setting one replaces any within
KEY_GAP_S of it, as the editor's crop tool does, and turns an auto scene
fixed (a tracked scene stays tracked, with the keyframe edited by hand).
Only a fill scene has a fill window to key. Resizing the box sets the
scene's scale, which sizes its window throughout the scene.

Between two keyframes the window moves linearly; before the first and
after the last it holds (window_at). Render evaluates the same ramp at
each frame with the crop expressions of pipeline/layout_parts, scene by
scene (pipeline/scene_framing), and ffmpeg's crop filter then rounds it
to the nearest pixel, keeps the window inside the frame and, for 4:2:0
video, rounds it down to even pixels.
"""

from collections.abc import Sequence

from clipforge.models import CropPlan, CropPoint, SceneReframe
from clipforge.pipeline.framing import interpolate

# Keyframes closer than this (seconds) are one: setting one replaces the
# others, and deleting at a time removes the one this close.
KEY_GAP_S = 0.1


class KeyframeError(ValueError):
    """A keyframe cannot be set there: outside the clip's scenes, or on a
    scene that is not in the fill layout."""


class NoKeyframe(LookupError):
    """There is no keyframe at the time to delete."""


def scene_index(scenes: Sequence[SceneReframe], t: float) -> int:
    """Return the index of the scene of scenes (in order, covering a clip)
    that holds t seconds of the source: the later one on a shared edge.
    Raises KeyframeError if t is outside the scenes."""
    for index in range(len(scenes) - 1, -1, -1):
        if scenes[index].start <= t <= scenes[index].end:
            return index
    raise KeyframeError(f"{t:g} s is not inside the clip")


def set_keyframe(
    scene: SceneReframe, point: CropPoint, scale: float | None = None
) -> SceneReframe:
    """Return scene with a keyframe at point (its time kept inside the
    scene, to the millisecond), replacing those within KEY_GAP_S of it, in
    fixed mode if it was auto, and at scale if set (module docstring).
    Raises KeyframeError if scene is not in the fill layout."""
    if scene.layout != "fill":
        raise KeyframeError(
            f"the scene at {scene.start:g} s is in the {scene.layout} layout; "
            "only a fill scene has a crop box"
        )
    t = round(min(max(point.t, scene.start), scene.end), 3)
    kept = [key for key in scene.crop_keyframes if abs(key.t - t) >= KEY_GAP_S]
    keyframes = sorted([*kept, point.model_copy(update={"t": t})], key=_time)
    return scene.model_copy(
        update={
            "mode": "fixed" if scene.mode == "auto" else scene.mode,
            "crop_keyframes": keyframes,
            "scale": scene.scale if scale is None else scale,
        }
    )


def delete_keyframe(scene: SceneReframe, t: float) -> SceneReframe:
    """Return scene without its keyframe nearest t. Raises NoKeyframe if
    none is within KEY_GAP_S of t."""
    near = [key for key in scene.crop_keyframes if abs(key.t - t) < KEY_GAP_S]
    if not near:
        raise NoKeyframe(f"the scene has no crop keyframe at {t:g} s")
    nearest = min(near, key=lambda key: abs(key.t - t))
    keyframes = [key for key in scene.crop_keyframes if key is not nearest]
    return scene.model_copy(update={"crop_keyframes": keyframes})


def window_at(plan: CropPlan, t: float, frame_width: int) -> tuple[float, float]:
    """Return the top-left corner (x, y), in source pixels, of plan's fill
    window at t seconds of the source in a frame_width wide source: linear
    between its keyframes and held outside them (module docstring), before
    ffmpeg rounds it; centered at plan.y if the plan has no keyframes."""
    keyframes = plan.keyframes
    if not keyframes:
        return (frame_width - plan.width) / 2, float(plan.y)
    times = [keyframe.t for keyframe in keyframes]
    xs = [float(keyframe.x) for keyframe in keyframes]
    ys = [float(plan.y if key.y is None else key.y) for key in keyframes]
    return interpolate(times, xs, t), interpolate(times, ys, t)


def _time(point: CropPoint) -> float:
    """Return the time of point (the sort key of keyframes)."""
    return point.t
