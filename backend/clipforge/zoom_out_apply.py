"""Plan a project's zoom-out moments again (TASK-198b), when the owner
changes their intensity after the clips were made.

A clip is planned again only if it has no manual scenes: every scene is
auto fill or one of the zoom-out layouts (square_blur, fit), without a
crop of its own. A clip without scenes must be in the layout that its
crop plan chose (else the owner chose one). Its stored scenes are dropped and
clip_layouts.set_planned_layouts plans it as it did for a new clip. Clips
in a layout of their own choice (split, grid, ...), clips with fixed or
tracked scenes and clips without a crop plan keep their framing.
"""

from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge.clip_layouts import load_plan, set_planned_layouts
from clipforge.db import ClipRow
from clipforge.models import DefaultLayout, Layout, SceneReframe, ZoomOutIntensity
from clipforge.pipeline.reframe import crop_path
from clipforge.pipeline.step import StepError

AUTO_LAYOUTS: tuple[Layout, ...] = ("fill", "square_blur", "fit")


def is_manual(scene: SceneReframe) -> bool:
    """Return True if scene is framed by the owner's choice: not auto fill
    or a zoom-out layout, or with a crop of its own."""
    return (
        scene.mode != "auto"
        or scene.layout not in AUTO_LAYOUTS
        or bool(scene.crop_keyframes)
        or scene.scale != 1
        or scene.track_seed is not None
    )


def plannable(clip: ClipRow, work: Path) -> bool:
    """Return True if clip has no manual scenes and its crop plan is in the
    job work directory work (module docstring)."""
    if clip.id is None or not crop_path(work, clip.id).is_file():
        return False
    if clip.scene_reframes:
        return not any(is_manual(scene) for scene in clip.scene_reframes)
    try:
        return clip.layout == load_plan(work, clip.id).layout
    except StepError:
        return False


def reapply_zoom_out(
    engine: Engine,
    work: Path,
    project_id: int,
    default: DefaultLayout,
    intensity: ZoomOutIntensity,
) -> Sequence[int]:
    """Plan the zoom-outs of project project_id's clips again at intensity
    (module docstring), in the job work directory work, and return the ids
    of the clips planned. Nothing is changed if default (the project's
    default layout) is a layout for every clip.

    Raises StepError if the work directory's meta.json is not valid.
    """
    if default not in ("auto", "dynamic"):
        return []
    with Session(engine) as session:
        rows = session.exec(
            select(ClipRow)
            .where(ClipRow.project_id == project_id)
            .order_by(col(ClipRow.id))
        ).all()
        clip_ids = [
            row.id for row in rows if row.id is not None and plannable(row, work)
        ]
        for row in rows:
            if row.id in clip_ids:
                row.scene_reframes = []
                session.add(row)
        session.commit()
    set_planned_layouts(engine, work, clip_ids, default, intensity)
    return clip_ids
