"""Auto zoom with ffmpeg (TASK-236): the frames that the zoom's scale
(eval=frame) hands to its crop are never smaller than the output, also after
a ramp back to 1 (whose sum drifts below 1 in doubles). A smaller frame made
the crop read past it and ffmpeg crash at random with SIGBUS."""

import re
import subprocess

from clipforge.ffmpeg import ffmpeg_bin
from clipforge.models import ZoomKeyframe
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.zoom_graph import zoom_filter

SIZE = (1080, 1920)
CLIP = ClipSpan(1, 0.0, 3.0)
ZOOM = [
    ZoomKeyframe(t=0.2, scale=1.0),
    ZoomKeyframe(t=0.4, scale=1.15),
    ZoomKeyframe(t=1.0, scale=1.15),
    ZoomKeyframe(t=1.5, scale=1.0),
    ZoomKeyframe(t=2.0, scale=1.0),
    ZoomKeyframe(t=2.2, scale=1.12),
]


def test_the_scaled_frames_are_never_smaller_than_the_output() -> None:
    plan = plan_crop(CLIP, "9:16", (1280, 720), [[] for _ in sample_times(0, 3)], [])
    scale, crop = zoom_filter(ZOOM, plan, "fit", 0.0, SIZE).split(",crop=", 1)
    graph = f"{scale},showinfo,crop={crop},showinfo"
    result = subprocess.run(
        [
            ffmpeg_bin(),
            "-hide_banner",
            "-nostdin",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=s=1080x1920:r=30:d=2.5",
            "-vf",
            graph,
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    sizes = [(int(w), int(h)) for w, h in re.findall(r" s:(\d+)x(\d+) ", result.stderr)]
    scaled, cropped = sizes[0::2], sizes[1::2]

    assert len(scaled) == len(cropped) == 75
    assert min(w for w, _ in scaled) == 1080 and min(h for _, h in scaled) == 1920
    # Frames 45-59 (1.5-2.0 s): back to 1, summed as (1 + 0.15) + (-0.15 + 0).
    assert set(scaled[45:60]) == {SIZE}
    assert (1242, 2208) in scaled
    assert set(cropped) == {SIZE}
