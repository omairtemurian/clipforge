"""Scene cuts (SPEC 6.3): PySceneDetect's ContentDetector on the source video.

The detector compares each frame with the one before it (on a downscaled
copy) and reports a cut where they differ by more than the threshold, 27,
once the scene before it has lasted 15 frames; so a cut in the first 15
frames of the timeframe is never reported. PySceneDetect decodes the video
with OpenCV, its fastest backend (docs/decisions.md). The timeframe is read
in slices of SLICE_S seconds, which find the same cuts as one pass, so that
progress can be reported after each.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from clipforge.pipeline.step import StepError

CUT_THRESHOLD = 27.0
SLICE_S = 30.0
# PySceneDetect's logger, which says "Detecting scenes..." for every slice.
LIBRARY_LOGGER = "pyscenedetect"


def detect_scene_cuts(
    path: Path,
    start: float,
    end: float,
    *,
    slice_s: float = SLICE_S,
    on_progress: Callable[[float], None] | None = None,
) -> list[float]:
    """Return the times (seconds) of the scene cuts in [start, end] s of path.

    path is a video file; a cut's time is the source time at which the first
    frame of the new scene starts. The video is read in slices of slice_s
    seconds; on_progress gets the fraction of the timeframe done after each.
    Raises StepError if the video cannot be opened or decoded.
    """
    # PySceneDetect loads OpenCV and PyAV, so only import it when needed.
    from scenedetect import (
        ContentDetector,
        FrameTimecode,
        SceneManager,
        VideoOpenFailure,
        open_video,
    )
    from scenedetect.video_stream import SeekError

    logging.getLogger(LIBRARY_LOGGER).setLevel(logging.WARNING)
    try:
        video = open_video(str(path), backend="opencv")
        if start > 0:
            video.seek(FrameTimecode(start, video.frame_rate))
        manager = SceneManager()
        manager.add_detector(ContentDetector(threshold=CUT_THRESHOLD))
        done = start
        while done < end:
            done = min(done + slice_s, end)
            manager.detect_scenes(video, end_time=FrameTimecode(done, video.frame_rate))
            if on_progress is not None:
                on_progress((done - start) / (end - start))
        scenes = manager.get_scene_list()
    except (OSError, VideoOpenFailure, SeekError) as exc:
        raise StepError(f"cannot detect the scene cuts of {path}: {exc}") from exc
    return [float(cut.seconds) for cut, _ in scenes[1:]]
