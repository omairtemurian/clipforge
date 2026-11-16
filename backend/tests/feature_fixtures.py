"""ffmpeg-made videos and music with known edit features (tests only): cut
times, zoom ramps and punches, a shake, a B&W window, flashes and a click
track at a known tempo. Every video is 640x360 at 30 fps, h264."""

from pathlib import Path

from clipforge.ffmpeg import run_ffmpeg

FPS = 30
SIZE = "640x360"
SCALE = f"scale={SIZE.replace('x', ':')}"
ENCODE: list[str | Path] = [
    "-c:v",
    "libx264",
    "-pix_fmt",
    "yuv420p",
    "-r",
    str(FPS),
    "-an",
]

# Cut fixture: shots of different test patterns, as (source, seconds); its
# cuts are at 1.0, 2.5, 2.9 and 4.0 s; frame 105 (3.5 s), inside the fourth
# shot, is a white flash, which is not a cut.
SHOTS = [
    ("testsrc2", 1.0),
    ("smptehdbars", 1.5),
    ("color=c=0x202020,drawgrid=w=40:h=40:t=4:c=white", 0.4),
    ("rgbtestsrc", 1.1),
    ("testsrc", 1.0),
]
CUTS = [1.0, 2.5, 2.9, 4.0]
CUT_FLASH_FRAME = 105

# Zoom fixture (frames): still until 30, a ramp 1.0 -> 1.3 over frames
# 31-60, held, a punch back to 1.0 at frame 90, a punch in to 1.2 at 120.
ZOOM = (
    "if(lt(on,30),1,if(lt(on,60),1+0.3*(on-30)/30,"
    "if(lt(on,90),1.3,if(lt(on,120),1,1.2))))"
)
# Shake fixture: the picture jolts left and right (6 Hz, 30 px of 1280)
# from 2 to 3 s and pans steadily (60 px a second) from 4 to 5 s.
SHAKE_X = "40+30*sin(2*PI*6*t)*between(t,2,3)+60*clip(t-4,0,1)"

# Color fixture: testsrc2, B&W from 2 to 3.5 s, pure red from 3.5 to 5 s.
BW_WINDOW = (2.0, 3.5)
RED_WINDOW = (3.5, 5.0)

# Flash fixture: white frames 45-46 and 120, a +0.45 brightness frame 150.
WHITE_FRAMES = [(45, 46), (120, 120)]
SPIKE_FRAME = 150


def _still(path: Path) -> Path:
    """Write one 1360x800 testsrc2 frame to path (PNG); return path."""
    run_ffmpeg(["-f", "lavfi", "-i", "testsrc2=s=1360x800", "-frames:v", "1", path])
    return path


def make_cuts(path: Path) -> Path:
    """Write the cut fixture (SHOTS, CUTS, CUT_FLASH_FRAME) to path."""
    inputs: list[str | Path] = []
    for source, seconds in SHOTS:
        name = source.split(",")[0]
        options = f"s={SIZE}:r={FPS}:d={seconds}"
        inputs += ["-f", "lavfi", "-i", f"{name}{':' if '=' in name else '='}{options}"]
    chains = []
    for index, (source, _) in enumerate(SHOTS):
        extra = source.split(",", 1)[1] + "," if "," in source else ""
        chains.append(f"[{index}:v]{extra}format=yuv420p,setsar=1[v{index}]")
    joined = "".join(f"[v{i}]" for i in range(len(SHOTS)))
    flash = f"drawbox=color=white:thickness=fill:enable='eq(n,{CUT_FLASH_FRAME})'"
    graph = ";".join(chains) + f";{joined}concat=n={len(SHOTS)}:v=1:a=0,{flash}[out]"
    run_ffmpeg([*inputs, "-filter_complex", graph, "-map", "[out]", *ENCODE, path])
    return path


def make_zoom(path: Path, seconds: float = 6.0) -> Path:
    """Write the zoom fixture (ZOOM) to path."""
    zoompan = (
        f"zoompan=z='{ZOOM}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d=1:s={SIZE}:fps={FPS}"
    )
    return _from_still(path, zoompan, seconds)


def make_shake(path: Path, seconds: float = 6.0) -> Path:
    """Write the shake fixture (SHAKE_X) to path."""
    crop = f"crop=1280:720:x='{SHAKE_X}':y=40,{SCALE}"
    return _from_still(path, crop, seconds)


def make_color(path: Path) -> Path:
    """Write the color fixture (BW_WINDOW, RED_WINDOW), 6 s of a still
    testsrc2 frame, to path."""
    (bw_start, bw_end), (red_start, red_end) = BW_WINDOW, RED_WINDOW
    bw = f"hue=s=0:enable='between(t,{bw_start},{bw_end - 0.001})'"
    red = (
        "drawbox=color=red:thickness=fill"
        f":enable='between(t,{red_start},{red_end - 0.001})'"
    )
    return _from_still(path, f"{SCALE},{bw},{red}")


def make_flashes(path: Path) -> Path:
    """Write the flash fixture (WHITE_FRAMES, SPIKE_FRAME), 6 s of a still
    testsrc2 frame, to path."""
    white = "+".join(f"between(n,{a},{b})" for a, b in WHITE_FRAMES)
    return _from_still(
        path,
        f"{SCALE},drawbox=color=white:thickness=fill:enable='{white}',"
        f"eq=brightness=0.45:enable='eq(n,{SPIKE_FRAME})'",
    )


def _from_still(path: Path, filters: str, seconds: float = 6.0) -> Path:
    """Write seconds of the 1360x800 still testsrc2 frame (_still) through
    filters (which must end at SIZE) to path; return path."""
    still = _still(path.with_suffix(".png"))
    loop: list[str | Path] = ["-loop", "1", "-framerate", str(FPS)]
    run_ffmpeg([*loop, "-t", str(seconds), "-i", still, "-vf", filters, *ENCODE, path])
    return path


def make_click_track(path: Path, bpm: float, seconds: float = 16.0) -> Path:
    """Write a click track at bpm to path (AAC): a 1.5 kHz click on every
    beat from 0 s, the first beat of every 4 three times louder, quiet
    (-20 dB) for the first 16 beats, then loud with a 55 Hz bass hit on each
    beat: the drop is beat 16."""
    period = 60 / bpm
    drop = 16 * period
    click = (
        f"(0.3+0.6*lt(mod(t,{4 * period}),{period / 2}))"
        f"*sin(2*PI*1500*t)*exp(-mod(t,{period})*60)*if(lt(t,{drop}),0.1,1)"
    )
    bass = f"if(gte(t,{drop}),0.4*sin(2*PI*55*t)*exp(-mod(t,{period})*6),0)"
    source = f"aevalsrc='{click}+{bass}':s=44100:d={seconds}"
    run_ffmpeg(["-f", "lavfi", "-i", source, "-c:a", "aac", path])
    return path
