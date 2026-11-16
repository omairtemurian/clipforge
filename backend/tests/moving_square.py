"""A synthetic moving subject for tracking tests (tests only): a white
square with a red center that moves right at SPEED px/s through a
640x360 video, its top at TOP."""

from pathlib import Path

from clipforge.ffmpeg import run_ffmpeg

WIDTH, HEIGHT = 640, 360
SPEED = 120
START_X, SIDE, TOP = 40, 60, 150


def square_x(t: float) -> float:
    """Return the square's center x at t seconds, in frame widths."""
    return (START_X + SPEED * t + SIDE / 2) / WIDTH


def make_moving_square(path: Path, duration: float = 4.0) -> Path:
    """Write a duration s 25 fps video of the square, moving right from
    x=START_X over a dark gray background, to path; return path."""
    size = f"{WIDTH}x{HEIGHT}"
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", f"color=c=0x303030:s={size}:d={duration}:r=25",
            "-f", "lavfi", "-i", f"color=c=white:s={SIDE}x{SIDE}:d={duration}:r=25",
            "-filter_complex",
            "[1]drawbox=x=15:y=15:w=30:h=30:color=red:t=fill[s];"
            f"[0][s]overlay=x='{START_X}+t*{SPEED}':y={TOP}:eval=frame",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", path,
        ]
    )  # fmt: skip
    return path
