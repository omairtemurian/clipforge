"""Tests of transitions at a clip's cuts (SPEC-v2 3.5, pipeline/transitions):
the xfade names exist in the installed ffmpeg, auto transitions go on jump
cuts and manual ones between sections, each is fitted to whole frames and
its parts, and real renders keep their length, blending the parts only
around the cut."""

import subprocess
from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import ffmpeg_bin, ffprobe_bin, probe_media, run_ffmpeg
from clipforge.models import ClipTransitions, FaceBox, Transition, TransitionKind
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.render_graph import cut_graph
from clipforge.pipeline.transitions import (
    XFADE,
    Join,
    clip_joins,
    fit_join,
    join_graph,
)
from frames import Pixels, frame_at

FPS = 30
SIZE = (160, 160)
RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)
KINDS: tuple[TransitionKind, ...] = ("crossfade", "zoom_punch", "whip", "slide")


def transitions(
    auto: TransitionKind | None = None,
    *sections: TransitionKind | None,
    duration: float = 0.4,
) -> ClipTransitions:
    """Return auto on jump cuts and sections between sections, duration
    seconds each."""

    def make(kind: TransitionKind | None) -> Transition | None:
        return None if kind is None else Transition(kind=kind, duration=duration)

    return ClipTransitions(auto=make(auto), sections=[make(k) for k in sections])


def test_each_xfade_transition_is_one_the_installed_ffmpeg_has() -> None:
    result = run_ffmpeg(["-hide_banner", "-h", "filter=xfade"])
    names = {line.split()[0] for line in result.stdout.decode().splitlines()[1:]
             if line.startswith("     ")}  # fmt: skip

    assert set(KINDS) == set(XFADE)
    assert set(XFADE.values()) <= names, ffmpeg_bin()


def test_auto_goes_on_jump_cuts_and_sections_on_section_cuts() -> None:
    # Section 0 (0-4 s) has a jump cut at 1-2 s; section 1 (6-8 s) has none.
    joins = clip_joins(
        0.0, 8.0, [(0.0, 4.0), (6.0, 8.0)], [(1.0, 2.0)],
        transitions("crossfade", "slide"), FPS,
    )  # fmt: skip

    assert joins == [Join("fade", 6, 0.2), Join("slideleft", 6, 0.2)]


def test_without_transitions_every_cut_is_hard() -> None:
    joins = clip_joins(
        0.0, 8.0, [(0.0, 4.0), (6.0, 8.0)], [(1.0, 2.0)], ClipTransitions(), FPS
    )

    assert joins == [None, None]


def test_section_transitions_follow_play_order_and_extras_are_unused() -> None:
    # Played: 6-8 s, then 0-2 s, then 3-4 s; the third entry has no cut.
    joins = clip_joins(
        0.0, 8.0, [(6.0, 8.0), (0.0, 2.0), (3.0, 4.0)], [],
        transitions(None, "whip", None, "slide"), FPS,
    )  # fmt: skip

    assert joins == [Join("hblur", 6, 0.2), None]


def test_a_section_cut_whole_takes_the_transition_after_the_one_before() -> None:
    # The middle section (2-3 s) is cut whole: the cut from 0-1 s to 5-6 s
    # takes the transition after section 0.
    joins = clip_joins(
        0.0, 6.0, [(0.0, 1.0), (2.0, 3.0), (5.0, 6.0)], [(2.0, 3.0)],
        transitions(None, "zoom_punch", "slide"), FPS,
    )  # fmt: skip

    assert joins == [Join("zoomin", 6, 0.2)]


def test_a_transition_is_cut_to_whole_frames_and_half_of_each_part() -> None:
    long = Transition(kind="crossfade", duration=1.0)

    assert fit_join(long, (0.0, 2.0), (3.0, 5.0), FPS) == Join("fade", 15, 0.5)
    assert fit_join(long, (0.0, 0.2), (3.0, 5.0), FPS) == Join("fade", 3, 0.1)
    assert fit_join(Transition(kind="whip", duration=0.1), (0, 1), (1, 2), 10) is None
    assert fit_join(long, (0.0, 1 / FPS), (3.0, 5.0), FPS) is None
    assert fit_join(None, (0.0, 2.0), (3.0, 5.0), FPS) is None


def test_the_join_graph_pads_the_parts_and_starts_half_before_the_cut() -> None:
    graph = join_graph(
        ["[a]", "[b]", "[c]"],
        [(0.0, 1.0), (2.0, 3.0), (4.0, 5.0)],
        [None, Join("fade", 3, 0.1)],
        "[out]",
    )

    assert graph.split(";") == [
        "[a]settb=AVTB[join_p0]",
        "[b]settb=AVTB,tpad=stop_mode=clone:stop=3[join_p1]",
        "[c]settb=AVTB,tpad=start_mode=clone:start=3[join_p2]",
        "[join_p0][join_p1]concat=n=2:v=1:a=0[join_x0]",
        "[join_x0][join_p2]xfade=transition=fade:duration=0.200000"
        ":offset=1.900000[out]",
    ]
    with pytest.raises(ValueError):
        join_graph(["[a]", "[b]"], [(0.0, 1.0), (2.0, 3.0)], [], "[out]")


def test_cut_graph_without_transitions_is_unchanged() -> None:
    spans = [(0.0, 1.0), (2.0, 3.0)]
    plain = cut_graph(spans, ("[0:a]", "[a]"), ("[f]", "[v]"))

    assert cut_graph(spans, ("[0:a]", "[a]"), ("[f]", "[v]"), [None]) == plain
    assert plain.endswith("concat=n=2:v=1:a=1[v][a]")


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 6 s 320x240 source: red for 2 s, green for 2 s, blue for 2 s,
    with a tone."""
    path = tmp_path_factory.mktemp("transitions") / "source.mp4"
    colours = [f"color=c={c}:size=320x240:rate={FPS}:duration=2"
               for c in ("red", "green", "blue")]  # fmt: skip
    run_ffmpeg(
        [arg for colour in colours for arg in ("-f", "lavfi", "-i", colour)]
        + ["-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6"]
        + ["-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]"]
        + ["-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        + ["-c:a", "aac", path]
    )
    return path


def render(
    source: Path,
    output: Path,
    cuts: list[tuple[float, float]],
    segments: list[tuple[float, float]],
    clip_transitions: ClipTransitions,
) -> Path:
    """Render the 0-6 s clip of source at SIZE with cuts, segments and
    clip_transitions."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(0.0, 6.0)]
    plan = plan_crop(ClipSpan(3, 0.0, 6.0), "1:1", (320, 240), faces, [])
    return render_clip(
        source, output, 0.0, 6.0, plan, "fill", RenderSettings(fps=FPS),
        cut_ranges=cuts, segments=segments, size=SIZE,
        transitions=clip_transitions,
    )  # fmt: skip


def stream_durations(video: Path) -> dict[str, float]:
    """Return the duration of video's video and audio streams (ffprobe)."""
    result = subprocess.run(
        [ffprobe_bin(), "-v", "error", "-show_entries", "stream=codec_type,duration",
         "-of", "csv=p=0", str(video)],
        capture_output=True, check=True, text=True,
    )  # fmt: skip
    pairs = (line.split(",") for line in result.stdout.split())
    return {kind: float(duration) for kind, duration in pairs}


def colour(frame: Pixels) -> Pixels:
    """Return the mean RGB colour of the middle of frame."""
    height, width, _ = frame.shape
    middle = frame[height // 4 : 3 * height // 4, width // 4 : 3 * width // 4]
    return middle.reshape(-1, 3).mean(axis=0)


def near(actual: Pixels, expected: tuple[int, int, int]) -> bool:
    """Return whether actual is within 40 of expected in every channel."""
    return bool(np.all(np.abs(actual - np.array(expected)) < 40))


@pytest.mark.parametrize("kind", KINDS)
def test_an_auto_transition_renders_at_the_jump_cut_and_keeps_the_length(
    source: Path, tmp_path: Path, kind: TransitionKind
) -> None:
    # 0-1.5 s (red), then 4.5-6 s (blue): the cut is at 1.5 s of the render.
    output = render(source, tmp_path / f"{kind}.mp4", [(1.5, 4.5)], [(0.0, 6.0)],
                    transitions(kind))  # fmt: skip

    assert probe_media(output).duration == pytest.approx(3.0, abs=0.05)
    durations = stream_durations(output)
    assert durations["video"] == pytest.approx(3.0, abs=1 / FPS)
    assert durations["audio"] == pytest.approx(3.0, abs=0.05)
    assert near(colour(frame_at(output, 1.0)), RED)
    assert near(colour(frame_at(output, 2.0)), BLUE)
    during = [colour(frame_at(output, t)) for t in (1.4, 1.5, 1.6)]
    assert not all(near(c, RED) or near(c, BLUE) for c in during), during
    assert not any(near(c, GREEN) for c in during)


def test_a_section_transition_and_a_hard_jump_cut_in_one_render(
    source: Path, tmp_path: Path
) -> None:
    # Blue 4.5-6 s with a hard jump cut at 5.0-5.2 s, then red 0-1.5 s with a
    # crossfade between the sections: 1.3 + 1.5 = 2.8 s, the section cut at
    # 1.3 s.
    sections = [(4.5, 6.0), (0.0, 1.5)]
    output = render(source, tmp_path / "sections.mp4", [(5.0, 5.2)], sections,
                    transitions(None, "crossfade"))  # fmt: skip

    assert probe_media(output).duration == pytest.approx(2.8, abs=0.05)
    assert stream_durations(output)["video"] == pytest.approx(2.8, abs=1 / FPS)
    assert near(colour(frame_at(output, 0.5)), BLUE)
    assert near(colour(frame_at(output, 2.2)), RED)
    mid = colour(frame_at(output, 1.3))
    assert not near(mid, BLUE) and not near(mid, RED), mid
    assert mid[0] > 60 and mid[2] > 60, mid
