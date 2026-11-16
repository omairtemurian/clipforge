"""The renders of a Pro Edit job (proedit/run_job.py): the variant's crop
plan, the proxy the critic judges and the final render that becomes the
variant's video.

A variant plays its original's sections, so it starts with a copy of the
original's crop plan (or, if the original has none, one reframed for it:
clip_crop.ensure_crop_plan). A proxy is rendered once per plan version
(job_dir/proxy_<plan id>.mp4: a version never changes). The final render
goes where every clip's video goes ({data_dir}/output/{project}/{clip}.mp4)
with the clip rendering while it runs, then rendered with its SRT and
metadata JSON next to it, like render_clip_row's.
"""

import shutil
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import config, webhook_events
from clipforge.clip_crop import ensure_crop_plan
from clipforge.db import ClipRow
from clipforge.models import Clip, ProEditPlan
from clipforge.pipeline.export import metadata_path, srt_path, write_metadata, write_srt
from clipforge.pipeline.reframe import crop_path
from clipforge.pipeline.render import clip_output
from clipforge.proedit.audio.sounds import library_sounds
from clipforge.proedit.edl import parse_item
from clipforge.proedit.render.base import ProEditBase, clip_base
from clipforge.proedit.render.cutout import CutoutChoice
from clipforge.proedit.render.run import render_plan


def ensure_variant_crop(engine: Engine, clip: Clip, work: Path) -> None:
    """Give variant clip a crop plan in work (module docstring) unless it
    has one."""
    target = crop_path(work, clip.id)
    if target.is_file():
        return
    parent = clip.parent_clip_id
    if parent is not None and crop_path(work, parent).is_file():
        shutil.copyfile(crop_path(work, parent), target)
        return
    ensure_crop_plan(engine, clip.id, work)


def plan_base(engine: Engine, work: Path, clip: Clip, plan: ProEditPlan) -> ProEditBase:
    """Return the render base of clip from work with the library sounds that
    plan's items play."""
    with Session(engine) as session:
        sounds = library_sounds(session, [parse_item(item) for item in plan.items])
    return clip_base(work, clip, config.settings.render.fps, sounds)


def render_proxy(
    engine: Engine,
    work: Path,
    folder: Path,
    clip: Clip,
    plan: ProEditPlan,
    on_progress: Callable[[float], None] | None = None,
    cutout: CutoutChoice | None = None,
) -> Path:
    """Return the proxy render of plan in folder, rendering it unless it is
    there (on_progress: the share written; cutout: the subject cut-out)."""
    output = folder / f"proxy_{plan.id}.mp4"
    if output.is_file():
        return output
    return render_plan(
        plan_base(engine, work, clip, plan),
        plan,
        output,
        quality="proxy",
        on_progress=on_progress,
        cutout=cutout,
    )


def render_final(
    engine: Engine,
    work: Path,
    clip_id: int,
    plan: ProEditPlan,
    on_progress: Callable[[float], None] | None = None,
    cutout: CutoutChoice | None = None,
) -> Clip:
    """Render plan as clip clip_id's video (module docstring), with the
    subject cut-out cutout if set, and return the rendered clip. A failed
    render raises and leaves the clip rendering with no video (the job's
    failure handling fails it)."""
    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
        clip = row.to_model()
        output = clip_output(clip.project_id, clip_id)
        for stale in (srt_path(output), metadata_path(output)):
            stale.unlink(missing_ok=True)
        row.status, row.output_path = "rendering", None
        session.add(row)
        session.commit()
    render_plan(
        plan_base(engine, work, clip, plan),
        plan,
        output,
        on_progress=on_progress,
        cutout=cutout,
    )
    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
        row.status, row.output_path = "rendered", str(output)
        session.add(row)
        session.commit()
        session.refresh(row)
        rendered = row.to_model()
    write_srt(work, rendered, config.settings.render.fps)
    write_metadata(work, rendered, config.settings.credit_template)
    webhook_events.clip_rendered(engine, clip_id)
    return rendered
