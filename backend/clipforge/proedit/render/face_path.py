"""The subject's face in each frame of a Pro Edit render (SPEC-v3 3.3), for
the zooms and pans that center on it and must never crop it out.

The base's crop plan (in a clip framed scene by scene, the plan and layout
of the scene that holds the time: zoom_graph.framing_at) holds at each
keyframe (source seconds) the fill window's left edge (and top) and the
boxes seen, the subject marked (speaker.mark_subjects). The render moves
the window linearly between keyframes (layout_parts.crop_window), so the
window at a time is interpolated the same way (framing.interpolate). The
face is the subject's face box (else the first face box; person and object
boxes are not faces), moved linearly between two keyframes whose faces
are the same track, else that of the nearest keyframe. Its box in the
window over the window's size is its box in the frame, clamped to the
frame. Only the fill layout shows one window; in the other layouts no face
is known (None), as zoom_graph.subject_center centers their zooms.

Frame n of the render shows the source at the time its played part puts it
(ProEditBase.played); the frames of a speed_ramp or slowmo window show the
face of the frame they play (motion_time.content_frames, the nearest
frame), those of a freeze_frame window the face of the frame they hold.

The tracked object (pipeline/object_tracking: the box of kind "object"
that reframe follows in a shot without a face or person) is found in each
frame the same way (subject_faces with pick=tracked_object), for overlays
anchored to it (overlay.py).
"""

from bisect import bisect_right
from collections.abc import Callable, Sequence

from clipforge.models import CropKeyframe, CropPlan, FaceBox
from clipforge.pipeline.framing import interpolate
from clipforge.pipeline.zoom_graph import framing_at
from clipforge.proedit.edl import FreezeFrameItem, TypedEdlItem
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.canvas import Box
from clipforge.proedit.render.motion_time import content_frames
from clipforge.proedit.render.timing import frame_range

# A face box in source pixels: x, y, width, height.
Pixels = tuple[float, float, float, float]
Pick = Callable[[CropKeyframe], FaceBox | None]


def subject(keyframe: CropKeyframe) -> FaceBox | None:
    """Return the face of keyframe the framing follows: the face marked
    subject, else its first face; None if it saw no face."""
    faces = [face for face in keyframe.faces if face.kind == "face"]
    return next((face for face in faces if face.subject), faces[0] if faces else None)


def tracked_object(keyframe: CropKeyframe) -> FaceBox | None:
    """Return the moving object that keyframe saw (its first box of kind
    "object"), or None."""
    return next((box for box in keyframe.faces if box.kind == "object"), None)


def _pixels(face: FaceBox) -> Pixels:
    return face.x, face.y, face.width, face.height


def _mix(a: Pixels, b: Pixels, share: float) -> Pixels:
    """Return the box share (0..1) of the way from a to b."""
    x, y, width, height = (p + (q - p) * share for p, q in zip(a, b, strict=True))
    return x, y, width, height


def _face_between(
    before: CropKeyframe | None,
    after: CropKeyframe | None,
    time: float,
    pick: Pick = subject,
) -> Pixels | None:
    """Return the box (pick: the subject's face) at time between the
    keyframes before and after it (either None past the plan's ends): moved
    linearly if both see the same track, else the nearest keyframe's."""
    first = None if before is None else pick(before)
    second = None if after is None else pick(after)
    if before and after and first and second and first.track == second.track:
        share = (time - before.t) / (after.t - before.t) if after.t > before.t else 1
        return _mix(_pixels(first), _pixels(second), share)
    near = [k for k in (before, after) if k is not None]
    nearest = min(near, key=lambda k: abs(k.t - time))
    face = pick(nearest)
    return None if face is None else _pixels(face)


class PlanFaces:
    """The subject's face (or the box that pick finds) in the fill window
    of a crop plan."""

    def __init__(self, plan: CropPlan, pick: Pick = subject) -> None:
        """Index the keyframes of plan."""
        self.plan = plan
        self.pick = pick
        self.times = [keyframe.t for keyframe in plan.keyframes]
        self.xs = [float(keyframe.x) for keyframe in plan.keyframes]
        self.ys = [
            float(plan.y if keyframe.y is None else keyframe.y)
            for keyframe in plan.keyframes
        ]

    def at(self, time: float) -> Box | None:
        """Return the subject's face in the fill window at time seconds of
        the source (module docstring), or None."""
        keyframes = self.plan.keyframes
        if not keyframes:
            return None
        index = bisect_right(self.times, time)
        before = keyframes[index - 1] if index > 0 else None
        after = keyframes[index] if index < len(keyframes) else None
        face = _face_between(before, after, time, self.pick)
        if face is None:
            return None
        x, y, width, height = face
        left = interpolate(self.times, self.xs, time)
        top = interpolate(self.times, self.ys, time)
        box = Box(
            left=_unit((x - left) / self.plan.width),
            top=_unit((y - top) / self.plan.height),
            right=_unit((x + width - left) / self.plan.width),
            bottom=_unit((y + height - top) / self.plan.height),
        )
        return box if box.width > 0 and box.height > 0 else None


def source_times(base: ProEditBase, fps: int) -> list[float]:
    """Return the source second that each frame of the render of base at
    fps shows, in frame order."""
    times: list[float] = []
    for start, end in base.played(fps):
        count = round((end - start) * fps)
        times += [base.start + start + k / fps for k in range(count)]
    return times


def held_ranges(items: Sequence[TypedEdlItem], fps: int) -> list[tuple[int, int]]:
    """Return the (first, end) frame ranges of the freeze_frame items: their
    frames show frame first (fx_basic.freeze_filters)."""
    return [
        frame_range(item.t_start, item.t_end, fps)
        for item in items
        if isinstance(item, FreezeFrameItem)
    ]


def subject_faces(
    base: ProEditBase,
    fps: int,
    items: Sequence[TypedEdlItem] = (),
    pick: Pick = subject,
) -> list[Box | None]:
    """Return the subject's face (or the box that pick finds) in each frame
    of the render of base at fps with items (module docstring), None where
    none is known."""
    known: dict[int, PlanFaces] = {}
    faces: list[Box | None] = []
    for time in source_times(base, fps):
        plan, layout = framing_at(base.scenes, base.plan, base.layout, time)
        if layout != "fill":
            faces.append(None)
            continue
        if id(plan) not in known:
            known[id(plan)] = PlanFaces(plan, pick)
        faces.append(known[id(plan)].at(time))
    played = list(faces)
    for frame, shown in content_frames(items, fps).items():
        if frame < len(faces) and played:
            faces[frame] = played[min(round(shown), len(played) - 1)]
    for first, end in held_ranges(items, fps):
        held = faces[first] if first < len(faces) else None
        for frame in range(first, min(end, len(faces))):
            faces[frame] = held
    return faces


def _unit(value: float) -> float:
    """Return value clamped to [0, 1]."""
    return min(max(value, 0.0), 1.0)
