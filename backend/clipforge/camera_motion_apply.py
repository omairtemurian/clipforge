"""Track a project's crop plans again (steering: calmer auto-track), when
the owner changes the project's camera motion after the clips were made.

Every clip of the project with a crop plan gets its windows planned again
from the faces and subjects its plan holds (reframe.retrack: no new face
detection), moving with the new camera motion. The plan's layout and
facecam box come from the same faces, so they do not change; the owner's
scenes, crops and tracked subjects are the clip's, not the plan's, and are
kept. The rendered videos change once the clips are rendered again.
"""

from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge.clip_layouts import load_plan
from clipforge.db import ClipRow
from clipforge.models import CameraMotion
from clipforge.pipeline.reframe import crop_path, retrack, scene_cuts
from clipforge.pipeline.step import load_meta, write_json


def retrack_project(
    engine: Engine, work: Path, project_id: int, camera_motion: CameraMotion
) -> Sequence[int]:
    """Plan the windows of project project_id's clips with crop plans in
    the job work directory work again with camera_motion (module
    docstring); return the ids of the clips whose plans were written.

    Raises StepError if the work directory's meta.json, signals.json or a
    crop plan is not valid.
    """
    with Session(engine) as session:
        clip_ids = session.exec(
            select(ClipRow.id)
            .where(ClipRow.project_id == project_id)
            .order_by(col(ClipRow.id))
        ).all()
    planned = [
        clip_id
        for clip_id in clip_ids
        if clip_id is not None and crop_path(work, clip_id).is_file()
    ]
    if not planned:
        return []
    meta = load_meta(work)
    cuts = scene_cuts(work)
    for clip_id in planned:
        plan = retrack(
            load_plan(work, clip_id), (meta.width, meta.height), cuts, camera_motion
        )
        write_json(crop_path(work, clip_id), plan)
    return planned
