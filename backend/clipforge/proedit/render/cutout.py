"""The subject cut-out of a Pro Edit render (SPEC-v3 3.3 motion): with the
subject's mask of every frame (proedit/segment.py, made by the pre-pass of
cutout_pass.py), the background behind the subject is blurred or swapped
for a solid color, and the subject is drawn again on top of the overlays
and kinetic captions ("subject in front of text").

In the video chain (graph.video_chain) start_filters come right before the
overlay stage, on the frames as the grade left them (the frames the
pre-pass segmented), and end_filters right after the captions stage.
Filters (ffmpeg 9.0.2, verified with `ffmpeg -h filter=alphamerge|gblur|
drawbox` and test renders; docs/decisions.md): `movie` reads the mask
video, `settb=expr=1/fps,setpts=N` times its frame n at frame n of the
clip, `scale` brings it to the frames' size; `alphamerge` takes the gray
mask as the frame's alpha (the subject layer: yuva420p); the background is
`gblur` (BLUR_SIGMA_SHARE of the frame's height) or `drawbox` filling the
frame with the color; `overlay` (format=yuv420) draws the subject layer
on it and, at the end, on the overlays and captions. MAIN_FORMAT keeps the
frames in limited range.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clipforge.ffmpeg import filter_value
from clipforge.models import EdlKind, ProEditBackground, ProEditOptions
from clipforge.proedit.edl import TypedEdlItem
from clipforge.proedit.render.captions import CAPTION_KINDS
from clipforge.proedit.render.overlay import MAIN_FORMAT, OVERLAY_KINDS

# The kinds the subject is drawn in front of.
FRONT_KINDS: frozenset[EdlKind] = OVERLAY_KINDS | CAPTION_KINDS
BLUR_SIGMA_SHARE = 0.02
SUBJECT = "[co_subject]"
SUBJECT_FRONT = "[co_front]"


@dataclass(frozen=True)
class CutoutChoice:
    """What the owner chose (ProEditOptions): the subject in front of the
    overlays and captions, and the background kept, blurred or swapped
    for color ("#rrggbb")."""

    subject_front: bool = False
    background: ProEditBackground = "keep"
    color: str = "#101014"

    @property
    def active(self) -> bool:
        """Return whether the choice changes anything."""
        return self.subject_front or self.background != "keep"


@dataclass(frozen=True)
class Cutout:
    """What the render draws: the mask video of the subject (one gray frame
    per frame of the clip), whether the subject goes in front of the
    overlays and captions and what the background becomes."""

    mask: Path
    front: bool
    background: ProEditBackground
    color: str


def cutout_choice(options: ProEditOptions) -> CutoutChoice:
    """Return the cut-out the owner chose in options."""
    return CutoutChoice(
        subject_front=options.subject_front,
        background=options.background,
        color=options.background_color,
    )


def front_needed(choice: CutoutChoice, items: Sequence[TypedEdlItem]) -> bool:
    """Return whether choice puts the subject in front of something: an
    overlay or caption item of items."""
    return choice.subject_front and any(i.kind in FRONT_KINDS for i in items)


def start_filters(cutout: Cutout | None, size: tuple[int, int], fps: int) -> list[str]:
    """Return the links of the video chain that put the subject on the
    changed background of size (width, height) frames at fps and keep the
    subject layer for end_filters (module docstring); [] without a
    cut-out."""
    if cutout is None:
        return []
    width, height = size
    mask = filter_value(str(cutout.mask.absolute()))
    background = _background(cutout, height)
    layers = [SUBJECT] if background is not None else []
    layers += [SUBJECT_FRONT] if cutout.front else []
    if not layers:
        return []
    subject = layers[0] if len(layers) == 1 else f",split=2{''.join(layers)}"
    graph = (
        f"{MAIN_FORMAT},split=2[co_frame][co_back];"
        f"movie=filename={mask},settb=expr=1/{fps},setpts=N,"
        f"scale={width}:{height}:flags=bicubic,format=gray[co_mask];"
        f"[co_frame][co_mask]alphamerge{subject};"
    )
    if background is None:
        return [f"{graph}[co_back]null"]
    return [
        f"{graph}[co_back]{background}[co_bg];[co_bg]{SUBJECT}"
        f"overlay=format=yuv420:eof_action=pass,{MAIN_FORMAT}"
    ]


def end_filters(cutout: Cutout | None) -> list[str]:
    """Return the link of the video chain that draws the subject layer of
    start_filters on top of the overlays and captions; [] unless the
    cut-out puts the subject in front."""
    if cutout is None or not cutout.front:
        return []
    return [
        f"{MAIN_FORMAT}[co_drawn];[co_drawn]{SUBJECT_FRONT}"
        f"overlay=format=yuv420:eof_action=pass,{MAIN_FORMAT}"
    ]


def _background(cutout: Cutout, height: int) -> str | None:
    """Return the filter that turns a frame into the cut-out's background,
    or None when the background is kept."""
    if cutout.background == "blur":
        return f"gblur=sigma={max(1.0, height * BLUR_SIGMA_SHARE):.1f}"
    if cutout.background == "swap":
        color = cutout.color.removeprefix("#")
        return f"drawbox=x=0:y=0:w=iw:h=ih:color=0x{color}@1:t=fill"
    return None
