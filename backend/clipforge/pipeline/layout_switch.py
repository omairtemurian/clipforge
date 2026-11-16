"""Dynamic layout switching (SPEC-v2 3.3): a layout per segment of a clip,
chosen by who is seen in it, for the default layout "dynamic".

The clip is cut into shots at the source's scene cuts (scenes.default_scenes)
and each shot into segments where the number of speakers changes for at
least MIN_SWITCH_S: every crop keyframe (sample) gets the layout that it
alone would get (segment_layout), the runs of equal layouts that are
shorter than MIN_SWITCH_S join their longer neighbour, and each segment
left takes the layout of all its samples. A segment's layout is:

- grid when three faces, split when two, persist (in more than the
  preset's split share of its samples) and the fill window leaves part of
  the frame out (as reframe.choose_layout);
- else, when a face or person is seen in at least SEEN_SHARE of them, fill,
  or the preset's layout (its facecam variant for fit: screenshare, so a
  gaming preset shows the screen and the player);
- else, when a moving object is, fill (the window follows it), or the
  preset's layout;
- else (nobody and nothing to follow) fit, or the preset's layout.

Neighbouring segments of one shot with the same layout are one segment;
shots keep their own scenes. The scenes are in auto mode, so their fill
windows follow the clip's crop plan; the editor changes any scene's layout
afterwards (PATCH /clips/{id} scene_reframes), and these choices stay.
"""

from collections.abc import Callable, Sequence

from clipforge.models import CropKeyframe, CropPlan, FaceBox, Layout, SceneReframe
from clipforge.pipeline.reframe_presets import DEFAULT, ReframeParams, params_for
from clipforge.pipeline.scenes import default_scenes

# The shortest stretch, in seconds, with a new number of speakers that
# switches the layout within a shot.
MIN_SWITCH_S = 2.0
# The share of a segment's samples in which someone (or something) must be
# seen for the segment to follow them.
SEEN_SHARE = 0.5
# The layout with a face of a preset's layout without one.
WITH_FACE: dict[Layout, Layout] = {"fit": "screenshare"}

Samples = Sequence[Sequence[FaceBox]]


def segment_layout(
    faces: Samples,
    frame_width: int,
    fill_width: int,
    params: ReframeParams = DEFAULT,
) -> Layout:
    """Return the layout of a segment whose samples hold faces, in a
    frame_width source whose fill window is fill_width wide, as the module
    docstring says; the params' layout (or fill) for a segment without
    samples."""
    preset = params.layout
    if not faces:
        return preset or "fill"

    def share(test: Callable[[Sequence[FaceBox]], bool]) -> float:
        return sum(test(found) for found in faces) / len(faces)

    if fill_width < frame_width:
        if share(lambda found: _speakers(found) >= 3) > params.split_share:
            return "grid"
        if share(lambda found: _speakers(found) >= 2) > params.split_share:
            return "split"
    if share(lambda found: any(f.kind != "object" for f in found)) >= SEEN_SHARE:
        return WITH_FACE.get(preset, preset) if preset else "fill"
    if share(lambda found: any(f.kind == "object" for f in found)) >= SEEN_SHARE:
        return preset or "fill"
    return preset or "fit"


def switch_scenes(
    plan: CropPlan,
    start: float,
    end: float,
    frame_width: int,
    cuts: Sequence[float],
) -> list[SceneReframe]:
    """Return the scenes of the clip of plan, from start to end seconds,
    each in auto mode with the layout of its segment (module docstring), in
    a frame_width source with scene cuts at the times cuts. The plan's
    preset sets the split share and the layouts without speakers."""
    params = params_for(plan.preset)
    scenes: list[SceneReframe] = []
    for shot in default_scenes(start, end, cuts, "fill"):
        samples = [k for k in plan.keyframes if shot.start <= k.t < shot.end]
        scenes += [
            SceneReframe(start=begin, end=finish, layout=layout)
            for begin, finish, layout in _shot_segments(
                shot, samples, frame_width, plan.width, params
            )
        ]
    return scenes


def main_layout(scenes: Sequence[SceneReframe]) -> Layout:
    """Return the layout that scenes (at least one) show for the longest
    time in all (to the millisecond); the earliest one of a tie."""
    totals: dict[Layout, float] = {}
    for scene in scenes:
        totals[scene.layout] = totals.get(scene.layout, 0) + scene.end - scene.start
    return max(totals, key=lambda layout: round(totals[layout], 3))


def _shot_segments(
    shot: SceneReframe,
    samples: Sequence[CropKeyframe],
    frame_width: int,
    fill_width: int,
    params: ReframeParams,
) -> list[tuple[float, float, Layout]]:
    """Return the (start, end, layout) segments of shot whose crop
    keyframes are samples (module docstring)."""
    runs: list[tuple[float, Layout]] = []
    for sample in samples:
        layout = segment_layout([sample.faces], frame_width, fill_width, params)
        if not runs or runs[-1][1] != layout:
            runs.append((shot.start if not runs else round(sample.t, 3), layout))
    bounds = [begin for begin, _ in smooth_runs(runs, shot.end)] or [shot.start]
    segments: list[tuple[float, float, Layout]] = []
    for index, begin in enumerate(bounds):
        finish = bounds[index + 1] if index + 1 < len(bounds) else shot.end
        faces = [k.faces for k in samples if begin <= k.t < finish]
        layout = segment_layout(faces, frame_width, fill_width, params)
        if segments and segments[-1][2] == layout:
            segments[-1] = (segments[-1][0], finish, layout)
        else:
            segments.append((begin, finish, layout))
    return segments


def smooth_runs(
    runs: Sequence[tuple[float, Layout]], end: float, shortest: float = MIN_SWITCH_S
) -> list[tuple[float, Layout]]:
    """Return runs, (start, layout) of a shot that ends at end, with each
    run shorter than shortest seconds joined to its longer neighbour (the
    left one of a tie), shortest first, until none is shorter or one is
    left."""
    kept = list(runs)
    while len(kept) > 1:
        lengths = [
            (kept[i + 1][0] if i + 1 < len(kept) else end) - kept[i][0]
            for i in range(len(kept))
        ]
        index = min(range(len(kept)), key=lambda i: lengths[i])
        if lengths[index] >= shortest:
            break
        left = lengths[index - 1] if index > 0 else -1.0
        right = lengths[index + 1] if index + 1 < len(kept) else -1.0
        if left >= right:
            del kept[index]
        else:
            kept[index + 1] = (kept[index][0], kept[index + 1][1])
            del kept[index]
        kept = _coalesce(kept)
    return kept


def _coalesce(runs: Sequence[tuple[float, Layout]]) -> list[tuple[float, Layout]]:
    """Return runs with each run that has the layout of the one before it
    joined to that one."""
    joined: list[tuple[float, Layout]] = []
    for run in runs:
        if not joined or joined[-1][1] != run[1]:
            joined.append(run)
    return joined


def _speakers(found: Sequence[FaceBox]) -> int:
    """Return the number of faces (not people or objects) in found."""
    return sum(face.kind == "face" for face in found)
