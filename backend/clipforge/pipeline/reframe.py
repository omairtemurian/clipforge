"""Reframe (SPEC 6.8): the crop windows of each clip, in crop_<clip_id>.json.

The faces (or people) in 10 frames a second of a clip (pipeline/faces), and
in a shot without either the moving object (pipeline/object_tracking), give
the windows to follow (pipeline/tracking):

- fill: the window has the size and top of the aspect's center crop
  (render.center_crop) and follows the subject: the face that speaks, by
  its mouth's moves during the transcript's speech (pipeline/speaker),
  marked in the plan's faces so other aspects follow it too;
- split, grid and pip: the windows of these layouts follow the left and
  right, or the left, middle and right speakers, or the other speaker
  (pipeline/layout_windows);
- screenshare and gameplay: the facecam box holds the subject's face
  (layout_windows.facecam_box).

Scene cuts (the scene_cut events of signals.json) start new shots, at which
the windows jump. Reframe also picks the clip's layout: split when two faces
(not people) persist, in more than the split share of the samples, and the
fill window is narrower than the frame (otherwise both faces fit in it),
else fill. The user can pick fit (the whole frame over a blurred copy) in
the editor. A genre preset (pipeline/reframe_presets) sets the layout, the
split share and the camera motion instead of these defaults; the project's
camera motion setting (pipeline/camera_motion), if given, wins.

Reframe works per clip, once the clips are saved, so it is not one of the
steps in STEP_NAMES; the process job runs it (pipeline/reframe_run) before
rendering the clips.
"""

import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import NamedTuple

from clipforge.aspect import aspect_size
from clipforge.models import (
    Aspect,
    CameraMotion,
    CropKeyframe,
    CropPlan,
    FaceBox,
    Layout,
    ReframePreset,
    SignalList,
    Transcript,
)
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.layout_windows import (
    facecam_box,
    grid_windows,
    inset_window,
    split_windows,
)
from clipforge.pipeline.reframe_presets import DEFAULT, ReframeParams, params_for
from clipforge.pipeline.render import center_crop
from clipforge.pipeline.speaker import mark_subjects, speaking_flags
from clipforge.pipeline.step import (
    SIGNALS,
    TRANSCRIPT,
    load_json,
)
from clipforge.pipeline.tracking import reset_flags, track_subject

logger = logging.getLogger(__name__)


class ClipSpan(NamedTuple):
    """A clip to reframe: its id, and its start and end in source seconds."""

    clip_id: int
    start: float
    end: float


def crop_path(job_dir: Path, clip_id: int) -> Path:
    """Return the path of a clip's crop plan: job_dir/crop_<clip_id>.json."""
    return job_dir / f"crop_{clip_id}.json"


def wants_split(
    faces: Sequence[Sequence[FaceBox]], share: float = DEFAULT.split_share
) -> bool:
    """Return True if two faces persist in the samples whose faces are
    faces: more than share of them have two or more faces."""
    with_two = sum(sum(face.kind == "face" for face in found) >= 2 for found in faces)
    return with_two > share * len(faces)


def choose_layout(
    faces: Sequence[Sequence[FaceBox]],
    frame_width: int,
    fill_width: int,
    params: ReframeParams = DEFAULT,
) -> Layout:
    """Return the layout of a clip with these faces in its samples: the
    params' if it has one; else split if wants_split (with the params'
    share) and the fill window, fill_width of the frame_width pixels, leaves
    part of the frame out; fill otherwise."""
    if params.layout is not None:
        return params.layout
    split = fill_width < frame_width and wants_split(faces, params.split_share)
    return "split" if split else "fill"


def plan_crop(
    clip: ClipSpan,
    aspect: Aspect,
    frame_size: tuple[int, int],
    faces: Sequence[list[FaceBox]],
    cuts: Iterable[float],
    speech: Sequence[tuple[float, float]] | None = None,
    preset: ReframePreset | None = None,
    camera_motion: CameraMotion | None = None,
) -> CropPlan:
    """Return the crop plan of clip, framed for aspect, from the faces in
    each of its samples (sample_times) of a frame_size video with scene cuts
    at the times cuts and speech in the spans speech (None: all the time):
    its fill window, which follows the subject the plan's faces mark
    (speaker.mark_subjects), its split, grid and inset windows and its
    facecam box (pipeline/layout_windows) and its layout (choose_layout), as the genre
    preset says, if there is one. The windows move with camera_motion (None:
    the preset's)."""
    times = sample_times(clip.start, clip.end)
    resets = reset_flags(times, cuts)
    marked = mark_subjects(faces, resets, speaking_flags(times, speech))
    motion = params_for(preset, camera_motion).camera_motion
    return _plan(clip, aspect, frame_size, times, marked, cuts, preset, motion)


def replan(
    plan: CropPlan,
    aspect: Aspect,
    frame_size: tuple[int, int],
    cuts: Iterable[float],
) -> CropPlan:
    """Return plan framed for aspect instead: the plan of its clip from the
    faces and subjects of its keyframes (no new face detection or subject
    choice) in a frame_size video with scene cuts at the times cuts; plan
    itself if it has that aspect. The new plan has the preset and the
    camera motion of plan."""
    if aspect == plan.aspect:
        return plan
    return _from_keyframes(plan, aspect, frame_size, cuts, plan.camera_motion)


def retrack(
    plan: CropPlan,
    frame_size: tuple[int, int],
    cuts: Iterable[float],
    camera_motion: CameraMotion,
) -> CropPlan:
    """Return plan with windows that move with camera_motion: the plan of
    its clip for its aspect from the faces and subjects of its keyframes
    (like replan) in a frame_size video with scene cuts at the times cuts."""
    return _from_keyframes(plan, plan.aspect, frame_size, cuts, camera_motion)


def _from_keyframes(
    plan: CropPlan,
    aspect: Aspect,
    frame_size: tuple[int, int],
    cuts: Iterable[float],
    camera_motion: CameraMotion | None,
) -> CropPlan:
    """Return the plan of plan's clip for aspect from its keyframes' faces,
    with plan's preset and camera_motion (None: the preset's)."""
    clip = ClipSpan(plan.clip_id, plan.start, plan.end)
    times = [keyframe.t for keyframe in plan.keyframes]
    faces = [keyframe.faces for keyframe in plan.keyframes]
    return _plan(
        clip, aspect, frame_size, times, faces, cuts, plan.preset, camera_motion
    )


def scene_cuts(job_dir: Path) -> list[float]:
    """Return the times of the scene cuts in job_dir's signals.json; raises
    StepError if it is missing or not valid."""
    signals = load_json(job_dir / SIGNALS, SignalList, "signals")
    return [event.start for event in signals.root if event.kind == "scene_cut"]


def speech_spans(job_dir: Path, clip: ClipSpan) -> list[tuple[float, float]] | None:
    """Return the (start, end) of the transcript segments of job_dir that
    overlap clip, or None if it has no transcript.json."""
    if not (job_dir / TRANSCRIPT).is_file():
        return None
    transcript = load_json(job_dir / TRANSCRIPT, Transcript, "transcribe")
    return [
        (segment.start, segment.end)
        for segment in transcript.segments
        if segment.start < clip.end and segment.end > clip.start
    ]


def _plan(
    clip: ClipSpan,
    aspect: Aspect,
    frame_size: tuple[int, int],
    times: Sequence[float],
    faces: Sequence[list[FaceBox]],
    cuts: Iterable[float],
    preset: ReframePreset | None,
    camera_motion: CameraMotion | None,
) -> CropPlan:
    """Return the crop plan of plan_crop with samples at times; its
    camera_motion is stored as given (None: a plan made before the
    setting, which moves with the preset's)."""
    params = params_for(preset, camera_motion)
    width, height = frame_size
    crop = center_crop(width, height, *aspect_size(aspect))
    resets = reset_flags(times, cuts)
    xs = track_subject(faces, resets, width, crop.width, params.motion)
    keyframes = [
        CropKeyframe(t=t, x=x, faces=found)
        for t, x, found in zip(times, xs, faces, strict=True)
    ]
    return CropPlan(
        clip_id=clip.clip_id,
        start=clip.start,
        end=clip.end,
        aspect=aspect,
        width=crop.width,
        height=crop.height,
        y=crop.y,
        keyframes=keyframes,
        layout=choose_layout(faces, width, crop.width, params),
        split=split_windows(faces, resets, frame_size, aspect, params),
        grid=grid_windows(faces, resets, frame_size, aspect, params),
        inset=inset_window(faces, resets, frame_size, params),
        facecam=facecam_box(faces, frame_size),
        preset=preset,
        camera_motion=camera_motion,
    )
