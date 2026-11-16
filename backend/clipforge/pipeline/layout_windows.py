"""The windows of the split, grid and pip layouts of a crop plan (SPEC 6.8,
SPEC-v2 3.3), and the facecam box of its screenshare and gameplay layouts,
which reframe plans with the fill window
(pipeline/reframe) from the faces in each sample of a clip:

- split: two windows follow the left and the right of the two largest
  faces; each has the shape of half the output frame and is the largest
  such window in half the source's width;
- grid: three windows follow the left, the middle and the right of the
  three largest faces; each has the shape of its cell of the output
  (layouts.grid_cells) and is the largest such window in a third of the
  source's width;
- pip: the inset's square window follows the other speaker: in each
  sample, the largest face that is not the subject (the face marked
  subject, else the largest). Its side is INSET_ZOOM times the median
  height of those faces, at most the frame's height and half its width.
  A clip without such a face in any sample has no inset window: the inset
  shows the whole frame;
- screenshare and gameplay: the facecam box is a square around the
  subject's face (the face marked subject, else the largest): FACECAM_ZOOM
  times its median height, at most the frame's shorter side, centered on
  its median center, inside the frame. It holds still, as a stream's
  facecam does. A clip without a face has none (the video takes the whole
  output).

Samples without the faces a window follows hold it (tracking.track_centers);
the first shots without any take evenly spaced centers (split, grid) or
the other face's median center (pip). A window's top centers the median
height of its faces, inside the frame. The windows move with the plan's
camera motion (the genre preset's if it has none: pipeline/camera_motion).

add_layout_windows adds the grid and pip windows to a plan made before
they were (whose grid is empty), and add_facecam the facecam box, from the
faces its keyframes hold.
"""

from collections.abc import Iterable, Sequence
from statistics import median

from clipforge.aspect import aspect_size
from clipforge.models import Aspect, CropPlan, CropWindow, FaceBox, FrameBox
from clipforge.pipeline.layouts import grid_cells
from clipforge.pipeline.reframe_presets import DEFAULT, ReframeParams, params_for
from clipforge.pipeline.render import Crop, center_crop
from clipforge.pipeline.tracking import (
    center_x,
    face_groups,
    reset_flags,
    track_centers,
)

# The pip inset's window is this many times the other face's height.
INSET_ZOOM = 3.0
# The facecam box's side is this many times the subject's face height.
FACECAM_ZOOM = 3.0


def split_windows(
    faces: Sequence[Sequence[FaceBox]],
    resets: Sequence[bool],
    frame_size: tuple[int, int],
    aspect: Aspect,
    params: ReframeParams = DEFAULT,
) -> tuple[CropWindow, CropWindow]:
    """Return the top and bottom windows of the split layout (module
    docstring) of a clip of a frame_size video, with faces and resets (shot
    starts) in its samples, framed for aspect."""
    out_width, out_height = aspect_size(aspect)
    cells = [(out_width, out_height // 2)] * 2
    top, bottom = side_windows(faces, resets, frame_size, cells, params)
    return top, bottom


def grid_windows(
    faces: Sequence[Sequence[FaceBox]],
    resets: Sequence[bool],
    frame_size: tuple[int, int],
    aspect: Aspect,
    params: ReframeParams = DEFAULT,
) -> list[CropWindow]:
    """Return the three windows of the grid layout (module docstring), like
    split_windows."""
    cells = grid_cells(aspect_size(aspect))
    return side_windows(faces, resets, frame_size, cells, params)


def side_windows(
    faces: Sequence[Sequence[FaceBox]],
    resets: Sequence[bool],
    frame_size: tuple[int, int],
    cells: Sequence[tuple[int, int]],
    params: ReframeParams = DEFAULT,
) -> list[CropWindow]:
    """Return one window for each of cells, (width, height) of the output,
    that follows, from left to right, the len(cells) largest faces of each
    sample: the largest window of the cell's shape in a len(cells)th of the
    frame_size source's width (module docstring)."""
    width, height = frame_size
    count = len(cells)
    groups = face_groups(faces, count)
    windows = []
    for side, (cell_width, cell_height) in enumerate(cells):
        crop = center_crop(width // count, height, cell_width, cell_height)
        followed = [None if group is None else group[side] for group in groups]
        centers = [None if face is None else center_x(face) for face in followed]
        default = width * (2 * side + 1) / (2 * count)
        xs = track_centers(
            centers,
            resets,
            width,
            crop.width,
            default,
            params.motion,
        )
        y = _window_top(followed, crop, height)
        windows.append(CropWindow(width=crop.width, height=crop.height, y=y, xs=xs))
    return windows


def inset_window(
    faces: Sequence[Sequence[FaceBox]],
    resets: Sequence[bool],
    frame_size: tuple[int, int],
    params: ReframeParams = DEFAULT,
) -> CropWindow | None:
    """Return the pip inset's window (module docstring) of a clip of a
    frame_size video with faces and resets in its samples, or None if no
    sample has another face than the subject."""
    width, height = frame_size
    others = other_faces(faces)
    found = [face for face in others if face is not None]
    if not found:
        return None
    zoomed = round(INSET_ZOOM * median(face.height for face in found))
    side = max(2, min(height, width // 2, zoomed))
    side -= side % 2
    centers = [None if face is None else center_x(face) for face in others]
    default = median(center_x(face) for face in found)
    xs = track_centers(centers, resets, width, side, default, params.motion)
    crop = Crop(side, side, (width - side) // 2, (height - side) // 2)
    y = _window_top(others, crop, height)
    return CropWindow(width=side, height=side, y=y, xs=xs)


def other_faces(faces: Sequence[Sequence[FaceBox]]) -> list[FaceBox | None]:
    """Return the largest face (not person) of each sample that is not its
    subject (the face marked subject, else the largest face), or None."""
    return [_ranked(sample)[1] for sample in faces]


def subject_faces(faces: Sequence[Sequence[FaceBox]]) -> list[FaceBox | None]:
    """Return the subject face (not person) of each sample: the face marked
    subject, else the largest face; or None."""
    return [_ranked(sample)[0] for sample in faces]


def facecam_box(
    faces: Sequence[Sequence[FaceBox]], frame_size: tuple[int, int]
) -> FrameBox | None:
    """Return the facecam box (module docstring) of a clip of a frame_size
    video with faces in its samples, or None if no sample has a face."""
    width, height = frame_size
    found = [face for face in subject_faces(faces) if face is not None]
    if not found:
        return None
    zoomed = round(FACECAM_ZOOM * median(face.height for face in found))
    side = max(2, min(width, height, zoomed))
    middle_x = median(center_x(face) for face in found)
    middle_y = median(face.y + face.height / 2 for face in found)
    x = min(max(round(middle_x - side / 2), 0), width - side)
    y = min(max(round(middle_y - side / 2), 0), height - side)
    return FrameBox(x=x / width, y=y / height, width=side / width, height=side / height)


def _ranked(sample: Sequence[FaceBox]) -> tuple[FaceBox | None, FaceBox | None]:
    """Return the subject of sample (the face, not person, marked subject,
    else the largest face) and the largest other face, or None for each."""
    found = sorted(
        (face for face in sample if face.kind == "face"),
        key=lambda face: face.width * face.height,
        reverse=True,
    )
    subject = next((face for face in found if face.subject), None)
    if subject is None and found:
        subject = found[0]
    rest = [face for face in found if face is not subject]
    return subject, rest[0] if rest else None


def add_layout_windows(
    plan: CropPlan, frame_size: tuple[int, int], cuts: Iterable[float]
) -> CropPlan:
    """Return plan with the grid and pip windows of its keyframes' faces in
    a frame_size video with scene cuts at the times cuts; plan itself if it
    has grid windows."""
    if plan.grid:
        return plan
    times = [keyframe.t for keyframe in plan.keyframes]
    faces = [keyframe.faces for keyframe in plan.keyframes]
    resets = reset_flags(times, cuts)
    params = params_for(plan.preset, plan.camera_motion)
    update = {
        "grid": grid_windows(faces, resets, frame_size, plan.aspect, params),
        "inset": inset_window(faces, resets, frame_size, params),
    }
    return plan.model_copy(update=update)


def add_facecam(plan: CropPlan, frame_size: tuple[int, int]) -> CropPlan:
    """Return plan with the facecam box of its keyframes' faces in a
    frame_size video (for a plan made before the facecam layouts)."""
    faces = [keyframe.faces for keyframe in plan.keyframes]
    return plan.model_copy(update={"facecam": facecam_box(faces, frame_size)})


def _window_top(
    followed: Sequence[FaceBox | None], crop: Crop, frame_height: int
) -> int:
    """Return the even top of a crop window that centers the median height
    of the followed faces inside a frame_height frame, or crop's top if
    there are none."""
    middles = [face.y + face.height / 2 for face in followed if face]
    if not middles:
        return crop.y
    top = round(median(middles) - crop.height / 2)
    y = min(frame_height - crop.height, max(0, top))
    return y - y % 2
