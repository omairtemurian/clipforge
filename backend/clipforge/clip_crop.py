"""The crop plan of a clip made after its project was processed.

The process job reframes the clips it finds (process_clips.make_clips); a
clip made later, like one made from the moment of a library search
(search/moment.clip_from_moment), has no crop plan until its render job
writes it here, framed as its project's processing settings say.
"""

from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.clip_layouts import set_planned_layouts
from clipforge.clips import get_clip_row
from clipforge.db import ProjectRow
from clipforge.pipeline.reframe import ClipSpan, crop_path
from clipforge.pipeline.reframe_run import reframe_clips


def ensure_crop_plan(engine: Engine, clip_id: int, work: Path) -> bool:
    """Write the crop plan of clip clip_id in work, the work directory of
    its project's process job, if it has none, and set the clip's planned
    layout (clip_layouts.set_planned_layouts) for its project's aspect,
    reframe preset, default layout and zoom-out moments; return whether a
    plan was written. Raises StepError if the clip does not exist, and the
    errors of reframe_clips."""
    if crop_path(work, clip_id).is_file():
        return False
    with Session(engine) as session:
        clip = get_clip_row(session, clip_id).to_model()
        processing = session.get_one(ProjectRow, clip.project_id).settings
    reframe_clips(
        work,
        [ClipSpan(clip_id, clip.start, clip.end)],
        processing.aspect,
        preset=processing.reframe_preset,
        camera_motion=processing.camera_motion,
    )
    set_planned_layouts(
        engine,
        work,
        [clip_id],
        processing.default_layout,
        processing.zoom_out_moments,
    )
    return True
