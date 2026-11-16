"""Generated style references with known burned-in captions and endings
(tests only): yellow Montserrat ExtraBold lines with a black outline over a
moving test pattern, and still-picture videos that end on their first
picture (a loop) or on another one (a hard cut)."""

from pathlib import Path

from clipforge.ffmpeg import run_ffmpeg
from PIL import ImageFont

FONT = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "fonts"
    / "Montserrat-ExtraBold.ttf"
)
WIDTH, HEIGHT = 540, 960
SECONDS = 4.0
FONT_SIZE = 56
OUTLINE = 4
COLOR = (255, 255, 0)
TOP = 0.7
# (text, from, to seconds); nothing on screen before the first one.
CAPTIONS = [
    ("THIS IS WILD", 0.8, 1.8),
    ("Wait for it", 1.8, 2.8),
    ("NO WAY", 2.8, SECONDS),
]
ENCODE: list[str | Path] = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-an"]


def cap_height() -> int:
    """The height in pixels of the capital letters at FONT_SIZE (PIL)."""
    font = ImageFont.truetype(str(FONT), FONT_SIZE)
    _, top, _, bottom = font.getbbox("THIS")
    return int(bottom - top)


def line_center_y() -> float:
    """Where the middle of the capitals sits, over the frame height: drawtext
    puts the top of the line's tallest glyph (a capital) at TOP."""
    return (TOP * HEIGHT + cap_height() / 2) / HEIGHT


def make_captions(path: Path) -> Path:
    """Write the caption reference (CAPTIONS, 30 fps) to path; return path."""
    color = "0x{:02X}{:02X}{:02X}".format(*COLOR)
    lines = ",".join(
        f"drawtext=fontfile='{FONT}':text='{text}':expansion=none"
        f":fontsize={FONT_SIZE}:fontcolor={color}:borderw={OUTLINE}"
        f":bordercolor=black:x=(w-text_w)/2:y=h*{TOP}"
        f":enable='between(t,{start},{end - 0.001})'"
        for text, start, end in CAPTIONS
    )
    source = f"testsrc2=s={WIDTH}x{HEIGHT}:r=30:d={SECONDS}"
    run_ffmpeg(["-f", "lavfi", "-i", source, "-vf", lines, *ENCODE, path])
    return path


def make_ending(path: Path, *, loop: bool, seconds: float = 6.0) -> Path:
    """Write a video of testsrc2 frames that ends on its first frame (loop)
    or on a plain colored picture (hard cut); return path."""
    end = (
        "trim=end_frame=1,loop=loop=-1:size=1" if loop else "drawbox=c=0x7F2060:t=fill"
    )
    graph = (
        f"[0]split[a][b];[b]{end},trim=end={seconds / 3},setpts=PTS-STARTPTS[e];"
        f"[a]trim=end={seconds * 2 / 3},setpts=PTS-STARTPTS[s];[s][e]concat"
    )
    source = f"testsrc2=s=640x360:r=30:d={seconds}"
    run_ffmpeg(["-f", "lavfi", "-i", source, "-filter_complex", graph, *ENCODE, path])
    return path
