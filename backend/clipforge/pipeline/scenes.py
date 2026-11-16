"""A clip's scenes (STEERING item 7): the spans between the source's scene
cuts that the editor frames one by one (models.SceneReframe).

A clip without stored scenes is framed in its layout throughout; its
default scenes (GET /clips/{id}/scenes) split it at the scene cuts inside
it. A cut closer than MIN_SCENE_S to the clip's start, its end or the
previous kept cut is skipped, so no scene is shorter than that. Stored
scenes cover the clip: they are in order, each starting where the one
before it ends, from the clip's start to its end; trimming or extending
the clip moves the first scene's start and the last one's end with it
(fit_scenes).
"""

from collections.abc import Sequence
from itertools import pairwise

from clipforge.models import Layout, SceneReframe

# The shortest scene that default_scenes makes, in seconds.
MIN_SCENE_S = 0.5
# How far (seconds) a scene's edge may be from where it should be.
EDGE_TOLERANCE_S = 1e-3


def default_scenes(
    start: float, end: float, cuts: Sequence[float], layout: Layout
) -> list[SceneReframe]:
    """Return the scenes of a clip from start to end seconds, split at the
    scene cuts cuts (seconds, any order) inside it as the module docstring
    says, each in auto mode and layout."""
    bounds = [start]
    for cut in sorted(cuts):
        if cut - bounds[-1] >= MIN_SCENE_S and end - cut >= MIN_SCENE_S:
            bounds.append(cut)
    bounds.append(end)
    return [
        SceneReframe(start=round(a, 3), end=round(b, 3), layout=layout)
        for a, b in pairwise(bounds)
    ]


def scene_problems(
    scenes: Sequence[SceneReframe], start: float, end: float
) -> list[str]:
    """Return what is wrong with scenes for a clip from start to end
    seconds: they must cover it in order, without gaps or overlaps; an
    empty list if they do (or if there are none)."""
    if not scenes:
        return []
    problems = []
    if abs(scenes[0].start - start) > EDGE_TOLERANCE_S:
        problems.append(
            f"the first scene starts at {scenes[0].start:g}, "
            f"not at the clip's start ({start:g})"
        )
    for before, after in pairwise(scenes):
        if abs(after.start - before.end) > EDGE_TOLERANCE_S:
            problems.append(
                f"the scene at {after.start:g} does not start where the scene "
                f"before it ends ({before.end:g})"
            )
    if abs(scenes[-1].end - end) > EDGE_TOLERANCE_S:
        problems.append(
            f"the last scene ends at {scenes[-1].end:g}, "
            f"not at the clip's end ({end:g})"
        )
    return problems


def fit_scenes(
    scenes: Sequence[SceneReframe], start: float, end: float
) -> list[SceneReframe]:
    """Return scenes fitted to a clip trimmed or extended to start..end
    seconds: scenes that end before start or start after end are dropped,
    the first one left starts at start and the last one ends at end; none
    if no scene overlaps the clip."""
    kept = [scene for scene in scenes if scene.end > start and scene.start < end]
    if not kept:
        return []
    fitted = list(kept)
    fitted[0] = fitted[0].model_copy(update={"start": start})
    fitted[-1] = fitted[-1].model_copy(update={"end": end})
    return fitted


def snap_scenes(
    scenes: Sequence[SceneReframe], start: float, end: float
) -> list[SceneReframe]:
    """Return scenes (valid for start..end: scene_problems) with their
    edges set exactly: the first starts at start, each other one where the
    one before it ends, and the last ends at end."""
    snapped: list[SceneReframe] = []
    for index, scene in enumerate(scenes):
        begin = start if index == 0 else snapped[-1].end
        finish = end if index == len(scenes) - 1 else scene.end
        snapped.append(scene.model_copy(update={"start": begin, "end": finish}))
    return snapped
