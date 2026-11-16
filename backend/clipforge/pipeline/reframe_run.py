"""Running reframe (pipeline/reframe) on a job's clips: the faces in each
clip's samples (pipeline/faces, reusing the job's face cache:
pipeline/face_cache), its moving objects and its crop plan, written to
crop_<clip_id>.json, with the time each clip took per minute of video
logged (steering: a 20 min source reframes in under 2 min).
"""

import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from clipforge import config
from clipforge.config import Settings
from clipforge.models import Aspect, CameraMotion, ReframePreset
from clipforge.pipeline.face_cache import FaceCache
from clipforge.pipeline.faces import (
    DetectFaces,
    analysis_size,
    face_detector,
    find_faces,
    sample_times,
)
from clipforge.pipeline.object_tracking import add_objects
from clipforge.pipeline.reframe import (
    ClipSpan,
    crop_path,
    plan_crop,
    scene_cuts,
    speech_spans,
)
from clipforge.pipeline.reframe_presets import params_for
from clipforge.pipeline.step import SOURCE, is_done, load_meta, write_json
from clipforge.pipeline.tracking import reset_flags

logger = logging.getLogger(__name__)


def reframe_clip(
    job_dir: Path,
    clip: ClipSpan,
    aspect: Aspect,
    detect: DetectFaces,
    preset: ReframePreset | None = None,
    *,
    camera_motion: CameraMotion | None = None,
    cache: FaceCache | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Write the crop plan of clip (plan_crop) into job_dir and return its path.

    It reads the video's size (meta.json), its scene cuts (signals.json), its
    speech (transcript.json, if there is one) and the frames of source.mp4,
    in which detect finds the faces (those of frames in cache, if set, are
    reused, and the new ones put in it: find_faces); shots without faces
    follow their moving object (object_tracking.add_objects) unless the
    genre preset, if there is one, says not to. The windows move with
    camera_motion (None: the preset's). on_progress, if set, gets
    the share of the clip's frames searched so far. Raises StepError if
    meta.json or signals.json is missing or not valid, and FFmpegError if
    ffmpeg fails.
    """
    began = time.monotonic()
    meta = load_meta(job_dir)
    cuts = scene_cuts(job_dir)
    times = sample_times(clip.start, clip.end)
    frame_size = (meta.width, meta.height)
    faces = find_faces(
        job_dir / SOURCE,
        clip.start,
        len(times),
        frame_size,
        detect,
        cache=cache,
        on_progress=on_progress,
    )
    resets = reset_flags(times, cuts)
    if params_for(preset).objects:
        faces = add_objects(job_dir / SOURCE, frame_size, times, resets, faces)
    speech = speech_spans(job_dir, clip)
    plan = plan_crop(
        clip, aspect, frame_size, faces, cuts, speech, preset, camera_motion
    )
    output = crop_path(job_dir, clip.clip_id)
    write_json(output, plan)
    seconds = time.monotonic() - began
    logger.info(
        "reframed clip %d (%.1f-%.1fs) in %.1f s (%.1f s per minute of video): "
        "faces in %d of %d frames, objects in %d, crop %dx%d, layout %s, "
        "subject in %d",
        clip.clip_id,
        clip.start,
        clip.end,
        seconds,
        seconds / max((clip.end - clip.start) / 60, 1e-9),
        sum(any(face.kind != "object" for face in found) for found in faces),
        len(times),
        sum(any(face.kind == "object" for face in found) for found in faces),
        plan.width,
        plan.height,
        plan.layout,
        sum(any(face.subject for face in k.faces) for k in plan.keyframes),
    )
    return output


def reframe_clips(
    job_dir: Path,
    clips: Sequence[ClipSpan],
    aspect: Aspect,
    *,
    cfg: Settings | None = None,
    force: bool = False,
    preset: ReframePreset | None = None,
    camera_motion: CameraMotion | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> list[Path]:
    """Write the crop plan of each of clips (reframe_clip); return their paths.

    A clip whose crop plan exists is skipped, unless force. The face model
    of cfg.models_dir (cfg defaults to the app settings) is loaded once, if a
    clip needs it, and the faces found are kept in the job's face cache
    (pipeline/face_cache), saved after each clip, for the clips and later
    reframes that sample the same frames. on_progress, if set, gets the
    share of those clips' seconds done as their frames are searched, and 1
    at the end. preset is the genre preset that frames the clips (None: the
    defaults) and camera_motion how their windows move (None: the
    preset's). Raises StepError if the model is missing, and the errors of
    reframe_clip.
    """
    todo = []
    for clip in clips:
        if is_done(crop_path(job_dir, clip.clip_id), force=force):
            logger.info("crop plan of clip %d exists; skipping it", clip.clip_id)
        else:
            todo.append(clip)
    report = on_progress or (lambda _: None)
    if todo:
        with face_detector(config.settings if cfg is None else cfg) as detect:
            meta = load_meta(job_dir)
            cache = FaceCache(job_dir, meta.fps, analysis_size(meta.width, meta.height))
            total = sum(max(clip.end - clip.start, 0.0) for clip in todo) or 1.0
            done = 0.0
            for clip in todo:
                length = max(clip.end - clip.start, 0.0)

                def clip_progress(
                    share: float, before: float = done, size: float = length
                ) -> None:
                    report(min((before + share * size) / total, 1.0))

                clip_progress(0.0)
                try:
                    reframe_clip(
                        job_dir,
                        clip,
                        aspect,
                        detect,
                        preset,
                        camera_motion=camera_motion,
                        cache=cache,
                        on_progress=clip_progress,
                    )
                finally:
                    cache.save()
                done += length
    report(1.0)
    return [crop_path(job_dir, clip.clip_id) for clip in clips]
