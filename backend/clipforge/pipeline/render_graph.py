"""The ffmpeg filter graph of a clip's render (SPEC 6.11), run by render_clip.

clip_graph frames the clip's video in its layout (fill, fit, split, grid,
pip, screenshare or gameplay: pipeline/layouts), zooms
it as its zoom keyframes say (pipeline/zoom_graph, auto zoom), levels its
colours (COLOR_FILTER, auto color correction), keeps
the parts of the clip that its cuts leave (cut_graph, with its audio;
joined by the transitions at its cuts, pipeline/transitions), punches in
on them for a viral hook (pipeline/hooks), draws
the layers of its timeline on them (pipeline/timeline_graph: B-roll,
overlays, text), then its captions (subtitles_filter) and writes it to
[v]; the clip's audio, cut with its frames, passes through the render's
audio filters (the loudness pass of pipeline/loudnorm) and is mixed with
its music, sound effect and voiceover layers into [a]. audio_graph is the
clip's audio without the video or layers, for loudnorm's first pass.
"""

from collections.abc import Sequence
from pathlib import Path

from clipforge.ffmpeg import filter_value
from clipforge.fonts import render_fonts_dir
from clipforge.models import CropPlan, Layout, ZoomKeyframe
from clipforge.pipeline.layouts import VIDEO_OUT, layout_graph
from clipforge.pipeline.scene_graph import ScenePart, scene_graph
from clipforge.pipeline.timeline_graph import (
    Layer,
    has_sounds,
    has_visuals,
    mix_graph,
    visual_graph,
)
from clipforge.pipeline.transitions import Join, has_joins, join_graph
from clipforge.pipeline.zoom_graph import zoom_filter

# The stream of the framed clip that the captions are drawn on.
FRAMED = "[framed]"
# The framed clip before its zoom and colour filters.
UNZOOMED = "[unzoomed]"
# Auto color correction: stretch the levels of the frames to the full range
# (linked channels, so hues stay; smoothed over a second against flicker,
# at half strength), then a little more saturation and a gentle S-curve.
COLOR_FILTER = (
    "normalize=smoothing=30:independence=0:strength=0.5,"
    "eq=saturation=1.12,"
    "curves=preset=medium_contrast"
)
# The source's audio, and the clip's audio as the render writes it.
AUDIO_IN = "[0:a:0]"
AUDIO_OUT = "[a]"
# The clip's video and audio after its cuts.
CUT_VIDEO = "[cut]"
CUT_AUDIO = "[acut]"
# The clip's video after its viral hook's punch-in.
PUNCHED = "[punched]"
# The clip's video with its timeline's layers, and its audio before they
# are mixed in.
LAYERED = "[layered]"
UNMIXED = "[unmixed]"


def subtitles_filter(captions: Path, fonts_dir: Path | None = None) -> str:
    """Return the subtitles filter that draws the ASS file captions on the
    frames with libass, which also loads the fonts in fonts_dir (the bundled
    and the uploaded fonts, render_fonts_dir, unless given).

    Both paths are made absolute and escaped (filter_value), so ffmpeg reads
    any file name as written.
    """
    fonts_dir = render_fonts_dir() if fonts_dir is None else fonts_dir
    return (
        f"subtitles=filename={filter_value(str(captions.absolute()))}"
        f":fontsdir={filter_value(str(fonts_dir.absolute()))}"
    )


def cut_graph(
    spans: Sequence[tuple[float, float]],
    audio: tuple[str, str],
    video: tuple[str, str] | None = None,
    joins: Sequence[Join | None] = (),
    audio_spans: Sequence[tuple[float, float]] | None = None,
) -> str:
    """Return the filters that keep spans, (start, end) seconds from a clip's
    start, of the audio stream labelled audio[0] and join them, in order,
    into audio[1]; and the same for the video stream video[0] into video[1],
    if video is set. With audio_spans (one per span, as long in all), the
    audio keeps those instead (J and L cuts, proedit/pacing.py) and is
    joined by its own concat.

    trim and atrim (to the sample) cut each part, which starts again at 0
    (setpts), and concat joins the parts of both streams together, so each
    part's audio starts with its video. If joins (one per cut:
    transitions.clip_joins) has a transition, the video parts are joined
    by transitions.join_graph instead, which keeps their length, and the
    audio parts alone by concat.
    """
    count = len(spans)
    streams = [("v", "", *video)] if video else []
    streams.append(("a", "a", *audio))
    parts = []
    for kind, a, source, _ in streams:
        kept = spans if kind == "v" or audio_spans is None else audio_spans
        pieces = "".join(f"[cut_{kind}{n}]" for n in range(count))
        parts.append(f"{source}{a}split={count}{pieces}")
        parts += [
            f"[cut_{kind}{n}]{a}trim=start={begin:.6f}:end={end:.6f},"
            f"{a}setpts=PTS-STARTPTS[kept_{kind}{n}]"
            for n, (begin, end) in enumerate(kept)
        ]
    if video and (has_joins(joins) or audio_spans is not None):
        videos = [f"[kept_v{n}]" for n in range(count)]
        if has_joins(joins):
            parts.append(join_graph(videos, spans, joins, video[1]))
        else:
            parts.append(f"{''.join(videos)}concat=n={count}:v=1:a=0{video[1]}")
        sounds = "".join(f"[kept_a{n}]" for n in range(count))
        parts.append(f"{sounds}concat=n={count}:v=0:a=1{audio[1]}")
        return ";".join(parts)
    segments = "".join(
        f"[kept_{kind}{n}]" for n in range(count) for kind, *_ in streams
    )
    outs = "".join(out for *_, out in streams)
    parts.append(f"{segments}concat=n={count}:v={len(streams) - 1}:a=1{outs}")
    return ";".join(parts)


def audio_graph(
    spans: Sequence[tuple[float, float]], filters: str, source: str = AUDIO_IN
) -> str:
    """Return the graph of a clip's audio alone, the stream labelled source
    (the source's by default): cut to spans (cut_graph) if there are any,
    then through the audio filters, into [a]."""
    if not spans:
        return f"{source}{filters}{AUDIO_OUT}"
    return f"{cut_graph(spans, (source, CUT_AUDIO))};{CUT_AUDIO}{filters}{AUDIO_OUT}"


def clip_graph(
    plan: CropPlan,
    layout: Layout,
    start: float,
    size: tuple[int, int],
    fps: int,
    captions: Path | None = None,
    *,
    spans: Sequence[tuple[float, float]] = (),
    audio: str = "",
    zoom: Sequence[ZoomKeyframe] = (),
    scenes: Sequence[ScenePart] = (),
    auto_color: bool = False,
    layers: Sequence[Layer] = (),
    joins: Sequence[Join | None] = (),
    punch: str = "",
    voice: str = AUDIO_IN,
    audio_spans: Sequence[tuple[float, float]] | None = None,
) -> str:
    """Return the -filter_complex graph of the clip of plan that starts at
    start seconds: its frames in layout (layout_graph), or scene by scene
    in each scene's layout with its plan if scenes holds more than one
    (scene_graph; one scene replaces plan and layout), as size (width,
    height) frames at fps frames a second, zoomed as zoom says (zoom_filter,
    about the subject of the scene of each zoom keyframe; before the cuts,
    in source time, and under the captions), with its
    colours levelled by COLOR_FILTER if auto_color, cut to spans
    (cut_graph, with the transitions joins at its cuts) if there are any,
    through the filters punch if set (a viral hook's punch-in,
    pipeline/hooks: in the rendered clip's time), with the visual layers of
    layers drawn
    on them (timeline_graph.visual_graph, under the captions) and the ASS
    file captions if set, written to [v].

    The clip's audio, the stream labelled voice (the source's by default),
    is cut with its frames (or to audio_spans if set: cut_graph), passed
    through the audio filters audio, if set, and mixed with the sound
    layers of layers
    (timeline_graph.mix_graph) into [a]; with none of these, the graph has
    no audio.
    """
    visuals, sounds = has_visuals(layers), has_sounds(layers)
    framed = FRAMED if captions is not None or spans or visuals or punch else VIDEO_OUT
    if len(scenes) == 1:
        plan, layout = scenes[0].plan, scenes[0].layout
    post = [zoom_filter(zoom, plan, layout, start, size, scenes)]
    post.append(COLOR_FILTER if auto_color else "")
    zooming = ",".join(f for f in post if f)
    frames = framed if not zooming else UNZOOMED
    if len(scenes) > 1:
        parts = [scene_graph(scenes, start, size, fps, out=frames)]
    else:
        parts = [layout_graph(plan, layout, start, size, fps, out=frames)]
    if zooming:
        parts.append(f"{UNZOOMED}{zooming}{framed}")
    video, sound = FRAMED, voice
    if spans:
        video_out = CUT_VIDEO if captions is not None or visuals or punch else VIDEO_OUT
        sound_out = CUT_AUDIO if audio or sounds else AUDIO_OUT
        parts.append(
            cut_graph(
                spans, (voice, sound_out), (FRAMED, video_out), joins, audio_spans
            )
        )
        video, sound = CUT_VIDEO, CUT_AUDIO
    if punch:
        punched = PUNCHED if captions is not None or visuals else VIDEO_OUT
        parts.append(f"{video}{punch}{punched}")
        video = PUNCHED
    if visuals:
        layered = LAYERED if captions is not None else VIDEO_OUT
        parts.append(visual_graph(layers, size, video, layered))
        video = LAYERED
    if captions is not None:
        parts.append(f"{video}{subtitles_filter(captions)}{VIDEO_OUT}")
    if audio:
        filtered = UNMIXED if sounds else AUDIO_OUT
        parts.append(f"{sound}{audio}{filtered}")
        sound = filtered
    if sounds:
        parts.append(mix_graph(layers, sound, AUDIO_OUT))
    return ";".join(parts)
