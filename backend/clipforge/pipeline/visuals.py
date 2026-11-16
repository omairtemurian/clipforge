"""Visuals step (SPEC-v2 3.2, clip anything): what is seen in a job's
timeframe -> motion.json and frame_captions.json.

The step only works when the job's AI clipping has clip_anything on; else it
does nothing. It measures the motion energy of each second (pipeline/motion)
and, when the local vision model engine (ollama_vlm) is installed, captions
sampled frames (pipeline/frame_captions). Curate then reads them with the
audio events and scene cuts of signals.json as timeline lines (timeline).
"""

import dataclasses
import logging
from collections.abc import Sequence
from pathlib import Path

from clipforge import engines
from clipforge.models import FrameCaptionList, MotionTrack, SignalList, SourceMeta
from clipforge.pipeline import frame_captions
from clipforge.pipeline.curate_prompt import timeline_lines
from clipforge.pipeline.enrich import PromptLine
from clipforge.pipeline.motion import measure_motion, motion_spans
from clipforge.pipeline.step import (
    FRAME_CAPTIONS,
    MOTION,
    SIGNALS,
    SOURCE,
    StepError,
    StepSettings,
    is_done,
    load_json,
    load_meta,
    write_json,
)

VLM_ENGINE = "ollama_vlm"
# The share of the step's progress for the motion; the captions take the rest.
MOTION_SHARE = 0.2

logger = logging.getLogger(__name__)


def wanted(settings: StepSettings) -> bool:
    """Whether the job clips anything: AI clipping with clip_anything on."""
    processing = settings.processing
    return processing.clipping == "ai" and processing.clip_anything


def run(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
    """Write the motion energy of the job's timeframe to motion.json and,
    if the vision model engine is installed, the frame captions to
    frame_captions.json; return the path of motion.json.

    Does nothing, and writes nothing, unless the job clips anything
    (wanted). Each file is skipped if it exists, unless force. Raises
    StepError if ingest or signals has not run, the video cannot be decoded
    or the vision model fails.
    """
    output = job_dir / MOTION
    if not wanted(settings):
        logger.info("clip anything is off; no motion or frame captions")
        settings.report_progress(1.0)
        return output
    meta = load_meta(job_dir)
    video = job_dir / SOURCE
    if not video.is_file():
        raise StepError(f"{video} not found; run the ingest step first")
    if is_done(output, force=force):
        logger.info("%s exists; skipping motion", output)
    else:
        track = measure_motion(video, meta.timeframe_start, meta.timeframe_end)
        write_json(output, track)
        logger.info("measured the motion of %d seconds", len(track.scores))
    settings.report_progress(MOTION_SHARE)

    if engines.is_installed(VLM_ENGINE):
        scaled = dataclasses.replace(
            settings,
            on_progress=lambda done: settings.report_progress(
                MOTION_SHARE + (1 - MOTION_SHARE) * done
            ),
        )
        frame_captions.run(job_dir, scaled, force=force)
    else:
        logger.warning("the %s engine is not installed; no frame captions", VLM_ENGINE)
    settings.report_progress(1.0)
    return output


def timeline(job_dir: Path, meta: SourceMeta) -> list[PromptLine]:
    """Return the clip-anything lines of the job's timeframe, by time
    (curate_prompt.timeline_lines): its audio events and scene cuts from
    signals.json, motion spans from motion.json and frame captions from
    frame_captions.json, which is optional (no vision model).

    Raises StepError if signals.json or motion.json is missing or a file is
    not valid.
    """
    start, end = meta.timeframe_start, meta.timeframe_end
    events = load_json(job_dir / SIGNALS, SignalList, "signals").root
    track = load_json(job_dir / MOTION, MotionTrack, "visuals")
    captions_path = job_dir / FRAME_CAPTIONS
    captions = (
        load_json(captions_path, FrameCaptionList, "visuals").captions
        if captions_path.is_file()
        else []
    )
    return timeline_lines(
        [event for event in events if start <= event.start < end],
        motion_spans(track),
        [caption for caption in captions if start <= caption.time < end],
        end,
    )


def with_timeline(
    lines: Sequence[PromptLine], job_dir: Path, meta: SourceMeta
) -> list[PromptLine]:
    """Return the transcript lines with the timeline lines of the job
    (timeline) between them, by start; at one start, transcript first."""
    merged = [(line.start, 0, line) for line in lines]
    merged += [(line.start, 1, line) for line in timeline(job_dir, meta)]
    return [line for _, _, line in sorted(merged, key=lambda item: item[:2])]
