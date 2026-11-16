"""Tests of viral hooks (SPEC-v2 3.5, pipeline/hooks): at least five
templates load with fonts and whooshes that exist, hook text is wrapped and
taken from a clip's opening words, a hook becomes text layers, a whoosh and
a punch-in, and real renders keep their length with the hook's text, zoom
and whoosh only over its first seconds."""

from pathlib import Path

import numpy as np
import pytest
from clipforge.config import RenderSettings
from clipforge.ffmpeg import ffprobe_json, probe_media, run_ffmpeg
from clipforge.fonts import available_fonts
from clipforge.hooks_templates import (
    TEXT_SLOT,
    get_template,
    load_templates,
    sound_path,
)
from clipforge.models import ClipHook, FaceBox, TextProps
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.hooks import (
    Punch,
    caption_hook_text,
    clip_punch,
    hook_layers,
    punch_filter,
    wrap_text,
)
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.text_overlay import text_filter
from frames import frame_at

FPS = 30
SIZE = (180, 320)
LENGTH = 4.0


def test_at_least_five_templates_load_with_their_fonts_and_whooshes() -> None:
    templates = load_templates()
    fonts = available_fonts()

    assert len(templates) >= 5
    assert len({t.label for t in templates.values()}) == len(templates)
    for name, template in templates.items():
        assert 2.0 <= template.duration <= 3.0, name
        assert all(TEXT_SLOT in layer.text for layer in template.layers), name
        assert {layer.font for layer in template.layers} <= set(fonts), name
        sound = sound_path(template)
        assert sound is not None and sound.is_file(), name
        assert float(ffprobe_json(sound)["format"]["duration"]) < template.duration
        info = template.info(name)
        assert (info.name, info.sound) == (name, True)
    with pytest.raises(ValueError, match="unknown hook template"):
        get_template("nope")


def test_text_is_uppercased_and_wrapped_to_the_templates_lines() -> None:
    template = get_template("slam_pop").model_copy(
        update={"uppercase": True, "max_chars_per_line": 12, "max_lines": 2}
    )

    assert wrap_text("  wait  for it ", template) == ("WAIT FOR IT", 1.0)
    text, scale = wrap_text("nobody tells you this about money", template)
    assert text.split("\n") == ["NOBODY TELLS YOU", "THIS ABOUT MONEY"]
    assert scale == pytest.approx(12 / 16)


@pytest.mark.parametrize(
    ("words", "text"),
    [
        (["said,", "why", "are", "we", "on"], "said, why are we on"),
        (["Stop.", "Listen", "now"], "Stop"),
        (["Is", "this", "real?", "Yes"], "Is this real?"),
        (
            ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"],
            "one two three four five six seven eight",
        ),  # fmt: skip
        (["a" * 40, "b" * 19, "c"], "a" * 40 + " " + "b" * 19),
        (["and", "then", "—"], "and then"),
        ([" ", ""], ""),
    ],
)
def test_the_caption_text_is_the_opening_sentence(words: list[str], text: str) -> None:
    assert caption_hook_text(words) == text


def test_a_hook_is_text_layers_then_its_whoosh_until_its_end() -> None:
    hook = ClipHook(template="echo_stack", text="no way", duration=2.5)
    template = get_template("echo_stack")

    layers = hook_layers(hook, LENGTH, available_fonts())

    *texts, sound = layers
    assert len(texts) == len(template.layers) >= 2
    for layer, base in zip(texts, template.layers, strict=True):
        assert layer.track == "text" and isinstance(layer.props, TextProps)
        assert (layer.item.start, layer.item.end) == (0, 2.5)
        assert layer.props.text == base.text.replace(TEXT_SLOT, "no way")
    assert (sound.track, sound.path) == ("sfx", sound_path(template))
    assert hook_layers(hook, 1.5, available_fonts())[0].item.end == 1.5
    assert hook_layers(None, LENGTH, available_fonts()) == []
    assert hook_layers(hook.model_copy(update={"template": "gone"}), LENGTH, {}) == []
    assert all(layer.track == "sfx" for layer in hook_layers(hook, LENGTH, {}))


def test_the_punch_fits_the_hook_and_scales_about_the_centre() -> None:
    hook = ClipHook(template="slam_pop", text="no way", duration=2.0)
    punch = get_template("slam_pop").punch
    assert punch is not None

    assert clip_punch(hook, LENGTH) == Punch(
        punch.scale, punch.attack, punch.release, 2.0
    )
    short = clip_punch(hook, 0.2)
    assert short is not None
    assert short.attack + short.release == pytest.approx(0.2)
    assert clip_punch(None, LENGTH) is None
    assert punch_filter(None, SIZE) == ""
    graph = punch_filter(Punch(1.2, 0.1, 0.3, 2.0), SIZE)
    assert "eval=frame" in graph and "crop=w=180:h=320" in graph
    assert graph.endswith("setsar=1")


def test_multi_line_text_is_centred_with_a_raw_newline() -> None:
    props = TextProps(text="ONE: TWO\nTHREE", font="Anton")

    graph = text_filter(props, available_fonts()["Anton"], SIZE[1], 0.0, 1.0)

    assert "text_align=C" in graph and "line_spacing=" in graph
    assert "TWO\nTHREE:" in graph


@pytest.fixture(scope="module")
def source(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 4 s 320x240 source: a black frame with a white centre square and a
    quiet tone."""
    path = tmp_path_factory.mktemp("hooks") / "source.mp4"
    run_ffmpeg(
        ["-f", "lavfi", "-i", f"color=c=black:size=320x240:rate={FPS}:d={LENGTH}"]
        + ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:d={LENGTH}"]
        + ["-filter_complex", "[0:v]drawbox=x=130:y=90:w=60:h=60:c=white:t=fill[v]"]
        + ["-map", "[v]", "-map", "1:a", "-af", "volume=0.05"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path]
    )
    return path


def render(source: Path, output: Path, hook: ClipHook | None) -> Path:
    """Render the whole of source at SIZE (9:16) with hook."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(0.0, LENGTH)]
    plan = plan_crop(ClipSpan(1, 0.0, LENGTH), "9:16", (320, 240), faces, [])
    return render_clip(
        source, output, 0.0, LENGTH, plan, "fill", RenderSettings(fps=FPS),
        size=SIZE, layers=hook_layers(hook, LENGTH, available_fonts()),
        punch=clip_punch(hook, LENGTH),
    )  # fmt: skip


def white_width(video: Path, time_s: float) -> int:
    """Return how many pixels across the middle row of the frame of video
    at time_s are white (the source's square)."""
    frame = frame_at(video, time_s)
    row = frame[frame.shape[0] // 2]
    return int(np.count_nonzero(row.min(axis=1) > 200))


def changed(video: Path, plain: Path, time_s: float) -> int:
    """Return how many pixels of video's frame at time_s differ by more
    than 60 from plain's in any channel."""
    diff = np.abs(frame_at(video, time_s).astype(int) - frame_at(plain, time_s))
    return int(np.count_nonzero(diff.max(axis=2) > 60))


def peak_volume(video: Path, start: float, end: float) -> float:
    """Return the peak level in dB of video's audio from start to end s."""
    result = run_ffmpeg(
        ["-ss", f"{start}", "-t", f"{end - start}", "-i", video]
        + ["-af", "volumedetect", "-vn", "-f", "null", "-"],
        loglevel="info",
    )
    line = next(
        line for line in result.stderr.decode().splitlines() if "max_volume" in line
    )
    return float(line.split("max_volume:")[1].split()[0])


@pytest.mark.parametrize("name", sorted(load_templates()))
def test_a_hook_renders_over_the_first_seconds_and_keeps_the_length(
    source: Path, tmp_path: Path, name: str
) -> None:
    plain = render(source, tmp_path / "plain.mp4", None)
    hook = ClipHook(template=name, text="Wait for it", duration=2.0)

    hooked = render(source, tmp_path / f"{name}.mp4", hook)

    assert probe_media(hooked).duration == pytest.approx(LENGTH, abs=0.05)
    assert changed(hooked, plain, 1.2) > 200
    assert changed(hooked, plain, 3.0) < 20
    assert peak_volume(hooked, 0.0, 0.5) > peak_volume(plain, 0.0, 0.5) + 6
    punch = clip_punch(hook, LENGTH)
    if punch is not None:
        peak = punch.attack
        assert white_width(hooked, peak) > white_width(plain, peak) + 2
        assert white_width(hooked, 3.0) == pytest.approx(white_width(plain, 3.0), abs=1)
