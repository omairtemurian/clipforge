"""Export a saved clip as an MP4 at a chosen resolution or for a platform
(SPEC-v2 3.9).

The clip is rendered again, framed and captioned exactly as its own render
is (clip_render), but at the frame that export_size picks: as large as the
source allows (4K from a 4K source), or what the resolution or the platform's
limits (export_presets) cap it at, never scaled up. The export goes to the
project's exports directory (pipeline/export.export_output); the clip's own
video, status and subtitles are left alone.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.clip_render import prepare_render, run_render
from clipforge.clips import get_clip_row
from clipforge.export_presets import (
    check_export,
    check_resolution,
    export_size,
    get_preset,
)
from clipforge.ffmpeg import probe_media
from clipforge.pipeline.export import export_output
from clipforge.pipeline.step import SOURCE

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportedClip:
    """An exported video: its file, frame size, duration in seconds and
    size in bytes, the preset it was made for (or None) and what keeps it
    from fitting that preset (check_export; empty without a preset)."""

    path: Path
    width: int
    height: int
    duration: float
    size_bytes: int
    preset: str | None
    problems: list[str]


def export_clip(
    engine: Engine,
    clip_id: int,
    work: Path,
    *,
    resolution: str = "source",
    preset: str | None = None,
) -> ExportedClip:
    """Render clip clip_id from work, the work directory of its project's
    process job, as an export and return it.

    resolution is a key of export_presets.RESOLUTIONS ("source": the largest
    frame that the source video allows) and preset the id of a platform
    preset (export_presets.PRESETS) whose frame limits also apply and whose
    other limits the result is checked against. The file is
    {data_dir}/output/{project_id}/exports/{clip_id}-{preset or resolution}.mp4
    and an earlier export of the same name is replaced. Raises ValueError if
    resolution or preset is unknown, StepError if the clip or a file that its
    render reads is missing, and RenderError or FFmpegError if the render
    fails, leaving no file.
    """
    check_resolution(resolution)
    limits = None if preset is None else get_preset(preset)
    with Session(engine) as session:
        row = get_clip_row(session, clip_id)
        project_id = row.project_id
        job = prepare_render(session, row.to_model(), work)
    source = probe_media(work / SOURCE)
    size = export_size(
        job.plan.aspect, (source.width, source.height), resolution, limits
    )
    output = export_output(project_id, clip_id, preset or resolution)
    run_render(job, work, output, size)
    info = probe_media(output)
    size_bytes = output.stat().st_size
    problems = (
        []
        if limits is None
        else check_export(limits, (info.width, info.height), info.duration, size_bytes)
    )
    logger.info(
        "exported clip %d as %s (%dx%d, %d bytes)",
        clip_id,
        output,
        info.width,
        info.height,
        size_bytes,
    )
    return ExportedClip(
        output, info.width, info.height, info.duration, size_bytes, preset, problems
    )
