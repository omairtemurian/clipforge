"""The filter graphs of the screenshare and gameplay layouts (SPEC-v2 3.3):
the video and the facecam of a stream or screen recording, stacked.

The output has two cells, rows if it is taller than wide, else columns
(facecam_cells); the facecam's takes FACECAM_SHARE of the long side:

- screenshare: the video first (top or left), the whole frame fitted in its
  cell over a blurred copy (or black: the plan's background), so all of the
  screen is readable; the facecam second;
- gameplay: the facecam first, then the video: the middle of the frame,
  scaled to cover its cell and cropped to it.

The facecam cell shows the plan's facecam box (CropPlan.facecam: the one
reframe found around the subject's face, layout_windows.facecam_box, or the
one the user drew, Framing.facecam), scaled to cover the cell and cropped to
it around the box's center. Without a facecam box the video takes the whole
output.
"""

from clipforge.models import CropPlan, FrameBox, Layout
from clipforge.pipeline.layout_parts import even, fit_graph

FACECAM_LAYOUTS: tuple[Layout, ...] = ("screenshare", "gameplay")
# The facecam cell's share of the output's long side, by layout.
FACECAM_SHARE: dict[Layout, float] = {"screenshare": 0.5, "gameplay": 1 / 3}


def facecam_cells(
    layout: Layout, size: tuple[int, int]
) -> tuple[tuple[int, int], tuple[int, int]]:
    """Return the (width, height) of the video's cell and of the facecam's
    cell of layout in a size (width, height) output (module docstring); the
    facecam's long side is even."""
    width, height = size
    share = FACECAM_SHARE[layout]
    if height > width:
        cam = max(2, even(round(height * share)))
        return (width, height - cam), (width, cam)
    cam = max(2, even(round(width * share)))
    return (width - cam, height), (cam, height)


def box_crop(box: FrameBox) -> str:
    """Return the crop filter of box, whatever the frame's size."""
    return (
        f"crop=w=iw*{box.width:.4f}:h=ih*{box.height:.4f}:"
        f"x=iw*{box.x:.4f}:y=ih*{box.y:.4f}"
    )


def cover(size: tuple[int, int]) -> str:
    """Return the filters that scale frames to cover size (width, height)
    and crop their middle to it."""
    width, height = size
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )


def facecam_graph(
    plan: CropPlan,
    layout: Layout,
    size: tuple[int, int],
    head: str,
    out: str,
    tag: str,
) -> str:
    """Return the graph of layout, screenshare or gameplay (module
    docstring), for plan's clip in a size output: it reads the frames of
    the filter chain head and writes to the stream label out; tag is added
    to the labels inside the graph (layouts.layout_graph)."""
    width, height = size
    if plan.facecam is None:
        return _video_graph(plan, layout, head, size, out, tag)
    video_cell, cam_cell = facecam_cells(layout, size)
    video, cam, framed, cammed = (
        f"[{name}{tag}]" for name in ("video", "cam", "framed", "cammed")
    )
    cells = f"{framed}{cammed}" if layout == "screenshare" else f"{cammed}{framed}"
    stack = "vstack" if height > width else "hstack"
    return ";".join(
        [
            f"{head},split=2{video}{cam}",
            _video_graph(plan, layout, f"{video}null", video_cell, framed, tag),
            f"{cam}{box_crop(plan.facecam)},{cover(cam_cell)},setsar=1{cammed}",
            f"{cells}{stack}=inputs=2,setsar=1{out}",
        ]
    )


def _video_graph(
    plan: CropPlan,
    layout: Layout,
    head: str,
    cell: tuple[int, int],
    out: str,
    tag: str,
) -> str:
    """Return the graph of the video's cell of layout, of size cell, from
    the filter chain head to the label out (module docstring)."""
    if layout == "screenshare":
        return fit_graph(head, cell, plan.background, out, tag)
    return f"{head},{cover(cell)},setsar=1{out}"
