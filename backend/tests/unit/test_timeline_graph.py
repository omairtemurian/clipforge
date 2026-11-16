"""Tests of the ffmpeg graph of a clip's timeline layers
(pipeline/timeline_graph, render_graph.clip_graph) and of the preview key
that they change."""

from pathlib import Path

from builders import make_clip
from builders import track_item as item
from clipforge.models import (
    AudioProps,
    CropPlan,
    FaceBox,
    MusicProps,
    OverlayProps,
    TextProps,
)
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.music import duck_filter
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render_graph import clip_graph
from clipforge.pipeline.timeline_graph import Layer, layer_inputs, mix_graph
from clipforge.preview import preview_key

FPS = 30


def nine_by_sixteen() -> CropPlan:
    """The 9:16 plan, with no faces, of a 4 s clip of a 320x240 source."""
    faces: list[list[FaceBox]] = [[] for _ in sample_times(0.0, 4.0)]
    return plan_crop(ClipSpan(1, 0.0, 4.0), "9:16", (320, 240), faces, [])


TEXT = Layer(
    "text",
    item("t", "text", 0.5, 1.5, props={"text": "a:b"}),
    TextProps(text="a:b", box="#000000"),
    Path("/fonts/A.ttf"),
)
SOUND = Layer(
    "sfx",
    item("m", "audio", 1.25, 2, asset_id=3),
    AudioProps(volume=0.5, offset=4),
    Path("/music/m.mp3"),
)
MUSIC = Layer(
    "music",
    item("bg", "audio", 0, 3, asset_id=4),
    MusicProps(volume=0.3, fade_out=1),
    Path("/music/bg.flac"),
)


def test_music_inputs_loop_their_file_for_the_items_length() -> None:
    assert layer_inputs([MUSIC], FPS) == [
        "-stream_loop", "-1", "-ss", "0.000", "-t", "3.000",
        "-i", Path("/music/bg.flac"),
    ]  # fmt: skip


def test_layer_inputs_read_each_asset_for_its_item_length() -> None:
    image = Layer(
        "overlays",
        item("o", "image", 1, 3, asset_id=2),
        OverlayProps(),
        Path("/img/o.png"),
    )

    assert layer_inputs([TEXT, image, SOUND], FPS) == [
        "-loop", "1", "-framerate", "30", "-t", "2.000", "-i", Path("/img/o.png"),
        "-ss", "4.000", "-t", "0.750", "-i", Path("/music/m.mp3"),
    ]  # fmt: skip


def test_sounds_are_delayed_to_their_start_and_mixed_without_scaling() -> None:
    assert mix_graph([TEXT, SOUND], "[0:a:0]", "[a]") == (
        "[1:a:0]volume=volume=0.5,adelay=delays=1250:all=1[mix0];"
        "[0:a:0][mix0]amix=inputs=2:duration=first:normalize=0[a]"
    )


def test_ducking_music_is_compressed_with_a_copy_of_the_clips_sound_as_key() -> None:
    quiet = Layer("music", MUSIC.item, MusicProps(duck=False), MUSIC.path)

    assert mix_graph([SOUND, MUSIC, quiet], "[unmixed]", "[a]") == (
        "[unmixed]asplit=2[voice][key1];"
        "[1:a:0]volume=volume=0.5,adelay=delays=1250:all=1[mix0];"
        "[2:a:0]volume=volume=0.3,afade=t=out:st=2.000:d=1.000,"
        f"adelay=delays=0:all=1[duck1];[duck1][key1]{duck_filter()}[mix1];"
        "[3:a:0]volume=volume=1,adelay=delays=0:all=1[mix2];"
        "[voice][mix0][mix1][mix2]amix=inputs=4:duration=first:normalize=0[a]"
    )


def test_clip_graph_draws_layers_under_the_captions_and_mixes_after_loudnorm() -> None:
    graph = clip_graph(
        nine_by_sixteen(),
        "fill",
        0.0,
        (180, 320),
        FPS,
        Path("/c.ass"),
        spans=[(0.0, 1.0), (2.0, 4.0)],
        audio="loudnorm",
        layers=[TEXT, SOUND],
    )

    drawtext = graph.index("drawtext=")
    assert graph.index("concat=") < drawtext < graph.index("subtitles=")
    assert "fontsize=19:fontcolor=0xFFFFFF" in graph
    assert "box=1:boxcolor=0x000000:boxborderw=5" in graph
    assert "enable='between(t,0.500,1.500)'[layered];[layered]subtitles=" in graph
    assert "[acut]loudnorm[unmixed];" in graph
    assert graph.endswith("[unmixed][mix0]amix=inputs=2:duration=first:normalize=0[a]")


def test_clip_graph_without_layers_is_unchanged() -> None:
    plan = nine_by_sixteen()

    assert clip_graph(plan, "fill", 0.0, (180, 320), FPS) == clip_graph(
        plan, "fill", 0.0, (180, 320), FPS, layers=[]
    )
    assert "[a]" not in clip_graph(plan, "fill", 0.0, (180, 320), FPS)


def test_tracks_change_the_preview_key() -> None:
    plan = nine_by_sixteen()
    plain = make_clip("minimal")
    tracks = plain.tracks.model_copy(update={"text": [TEXT.item]})

    assert preview_key(plain, plan) != preview_key(
        plain.model_copy(update={"tracks": tracks}), plan
    )
    assert preview_key(plain, plan) != preview_key(plain, plan, layers=[TEXT])
