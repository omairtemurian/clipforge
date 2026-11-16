"""ffmpeg-made style references with known edit features (tests only), on
top of feature_fixtures: a reference cut to a click track with a flash and
a B&W shot, a glitch reference (an RGB split and one odd frame) and flat
grey looks with a known vignette and grain. Every video is 640x360 at 30
fps, h264."""

from pathlib import Path

import feature_fixtures as fx
from clipforge.ffmpeg import run_ffmpeg

BPM = 120
# Beat-cut reference: (source, seconds, B&W) shots cut at 1.0, 2.0, 2.5, 3.5
# (on beats of BPM) and 4.2 s (between two); frame 15 is a white flash
# (not a cut) and the fourth shot, 2.5-3.5 s, is black and white.
BEAT_SHOTS = [
    ("testsrc2", 1.0, False),
    ("smptehdbars", 1.0, False),
    ("color=c=0x2040C0,drawgrid=w=40:h=40:t=4:c=white", 0.5, False),
    ("rgbtestsrc", 1.0, True),
    ("testsrc", 0.7, False),
    ("smptebars", 1.8, False),
]
BEAT_CUTS = [1.0, 2.0, 2.5, 3.5, 4.2]
BEAT_FLASH_FRAME = 15
BEAT_BW = (2.5, 3.5)

# Glitch reference: testsrc2 with red and blue 6 px apart each way on frames
# 30-44 and frame 90 mirrored.
SPLIT_FRAMES = (30, 44)
SPIKE_FRAME = 90


def make_beat_cuts(path: Path) -> Path:
    """Write the beat-cut reference (BEAT_SHOTS) with a BPM click track."""
    clicks = fx.make_click_track(path.with_suffix(".m4a"), BPM, seconds=6.0)
    inputs: list[str | Path] = []
    chains = []
    for index, (source, seconds, bw) in enumerate(BEAT_SHOTS):
        name, _, extra = source.partition(",")
        options = f"s={fx.SIZE}:r={fx.FPS}:d={seconds}"
        inputs += ["-f", "lavfi", "-i", f"{name}{':' if '=' in name else '='}{options}"]
        look = (extra + "," if extra else "") + ("hue=s=0," if bw else "")
        chains.append(f"[{index}:v]{look}format=yuv420p,setsar=1[v{index}]")
    joined = "".join(f"[v{i}]" for i in range(len(BEAT_SHOTS)))
    flash = f"drawbox=color=white:thickness=fill:enable='eq(n,{BEAT_FLASH_FRAME})'"
    graph = (
        ";".join(chains) + f";{joined}concat=n={len(BEAT_SHOTS)}:v=1:a=0,{flash}[out]"
    )
    audio = len(BEAT_SHOTS)
    run_ffmpeg(
        [*inputs, "-i", clicks, "-filter_complex", graph, "-map", "[out]"]
        + ["-map", f"{audio}:a", *fx.ENCODE[:-1], "-c:a", "aac", "-shortest", path]
    )
    return path


def make_glitch(path: Path) -> Path:
    """Write the glitch reference (SPLIT_FRAMES, SPIKE_FRAME) to path."""
    first, last = SPLIT_FRAMES
    split = f"rgbashift=rh=6:bh=-6:enable='between(n,{first},{last})'"
    mirror = f"hflip=enable='eq(n,{SPIKE_FRAME})'"
    return fx._from_still(path, f"{fx.SCALE},{split},{mirror}")


def make_look(path: Path, angle: str | None, grain: int = 0) -> Path:
    """Write 3 s of flat grey to path, with a vignette of lens angle (an
    ffmpeg expression, none if None) and luma noise of strength grain."""
    filters = ["format=yuv420p"]
    if angle is not None:
        filters.append(f"vignette=angle={angle}")
    if grain:
        filters.append(f"noise=c0s={grain}:c0f=t")
    source = f"color=c=gray:s={fx.SIZE}:r={fx.FPS}:d=3"
    run_ffmpeg(
        ["-f", "lavfi", "-i", source, "-vf", ",".join(filters), *fx.ENCODE, path]
    )
    return path
