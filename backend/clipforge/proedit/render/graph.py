"""The one ffmpeg filter graph of a Pro Edit render (SPEC-v3 3.6).

The base (base.ProEditBase) is framed and cut by the normal render's graph
(render_graph.clip_graph, with no captions, layers, zoom, punch or auto
color) into VIDEO_OUT and, through its censor filter (or anull), AUDIO_OUT,
both in the rendered clip's time, the time of the EDL (the sound with the
base's J and L cuts, proedit/pacing.py). The video then runs
through PIXEL_FORMAT and the filters of each stage of STAGES in order,
into PRO_VIDEO: speed ramps and slow motion first (motion_time.py; every
later stage draws on the frames as they play), then freeze frames (so the
zoom, grade and grain of a window are drawn on its held frame), then the
zoom track and shakes (motion.py, motion_time.py; the grade's vignette and
grain then sit on the zoomed picture), then transitions (fx_transition.py:
they blend the zoomed parts), then the grade track, then overlays
(overlay.py: graphics keep their own colors and sit on the zoomed picture,
following its faces and objects), then kinetic captions (captions.py:
on the zoomed, graded picture, so they stay put while it moves), then
glitches and RGB splits (fx_glitch.py: digital damage on the graded
picture), then flashes (a flash is white or black whatever the grade),
then the loop ending (loop_end.py: the finished last frames blend into the
finished first frame). A subject cut-out (cutout.py) changes the background
before the overlays and redraws the subject after the captions; its masks
come from the frames of PRE_CUTOUT_STAGES (cutout_pass.py).
A stage draws the items of its kinds on the Canvas (the frames' rate and
size; the subject's face in each frame when a zoom, pan or face-anchored
overlay needs it and the tracked object when an object-anchored overlay
does: face_path.subject_faces; the zoom stage's cameras when an overlay is
anchored to a face or object); a plan with an item that no stage draws is
refused (undrawn) rather than rendered without it.
The sound (AUDIO_OUT) gets the SFX items' sounds, ducked under the base's
speech and muted in the silences before drops (proedit/audio/sfx_mix), the
music beds, ducked the same way (music_bed), the audio effects (fx) and
the loop ending's crossfade into the opening (loop_end.py), into PRO_AUDIO
(proedit/audio/mix); an SFX or music bed item whose
sound is not known is refused the same way. With dialogue the base's sound
first goes through the dialogue chain, and a master filter (the loudness
pass) ends the mix; proedit_audio_graph is the sound alone, for the first
loudness pass.
Long graphs go through a file (ffmpeg_args.spilled_args, in run_ffmpeg).
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from clipforge.models import EdlKind
from clipforge.pipeline.layouts import VIDEO_OUT
from clipforge.pipeline.render_graph import AUDIO_OUT, audio_graph, clip_graph
from clipforge.proedit.audio.mix import sound_graph
from clipforge.proedit.audio.sounds import sound_problems
from clipforge.proedit.edl import OverlayItem, TypedEdlItem
from clipforge.proedit.render import (
    captions,
    cutout,
    fx_basic,
    fx_glitch,
    fx_transition,
    grade,
    loop_end,
    motion,
    motion_time,
    overlay,
)
from clipforge.proedit.render.base import ProEditBase
from clipforge.proedit.render.canvas import Canvas
from clipforge.proedit.render.face_path import subject_faces, tracked_object

PRO_VIDEO = "[pro_v]"
PRO_AUDIO = "[pro_a]"
# The stages' filters work on 8-bit planar YUV, the encoder's format; the
# grain stage's component 0 is then luma.
PIXEL_FORMAT = fx_basic.YUV_FORMAT
NO_AUDIO_FILTER = "anull"
Draw = Callable[[Sequence[TypedEdlItem], Canvas], list[str]]


def at_fps(draw: Callable[[Sequence[TypedEdlItem], int], list[str]]) -> Draw:
    """Return draw, which needs only the frame rate, as a stage's filters."""
    return lambda items, canvas: draw(items, canvas.fps)


@dataclass(frozen=True)
class Stage:
    """A step of the video chain: the filters that draw the items of kinds
    on a canvas and the problems that keep some of them from being
    drawn."""

    name: str
    kinds: frozenset[EdlKind]
    filters: Draw
    problems: Callable[[Sequence[TypedEdlItem]], list[str]]


STAGES: tuple[Stage, ...] = (
    Stage(
        "time",
        motion_time.TIME_KINDS,
        at_fps(motion_time.time_filters),
        fx_basic.no_problems,
    ),
    Stage(
        "freeze",
        frozenset({"freeze_frame"}),
        at_fps(fx_basic.freeze_filters),
        fx_basic.no_problems,
    ),
    Stage(
        "motion",
        motion.MOTION_KINDS | motion_time.SHAKE_KINDS,
        motion_time.camera_filters,
        fx_basic.no_problems,
    ),
    Stage(
        "transition",
        frozenset({"transition"}),
        at_fps(fx_transition.transition_filters),
        fx_basic.no_problems,
    ),
    Stage(
        "grade",
        frozenset({"grade_change", "vignette", "grain"}),
        at_fps(grade.grade_filters),
        grade.grade_problems,
    ),
    Stage(
        "overlay",
        overlay.OVERLAY_KINDS,
        overlay.overlay_filters,
        overlay.overlay_problems,
    ),
    Stage(
        "captions",
        captions.CAPTION_KINDS,
        captions.caption_filters,
        fx_basic.no_problems,
    ),
    Stage(
        "glitch",
        frozenset({"glitch", "rgb_split", "transition"}),
        fx_glitch.glitch_filters,
        fx_basic.no_problems,
    ),
    Stage(
        "flash",
        frozenset({"flash"}),
        at_fps(fx_basic.flash_filters),
        fx_basic.no_problems,
    ),
    Stage(
        "loop",
        frozenset({"transition"}),
        loop_end.loop_filters,
        fx_basic.no_problems,
    ),
)
PRE_CUTOUT_STAGES = STAGES[: [s.name for s in STAGES].index("overlay")]
AUDIO_KINDS: frozenset[EdlKind] = frozenset(
    {"sfx", "music_bed", "silence_before_drop", "audio_fx"}
)
DRAWN_KINDS: frozenset[EdlKind] = AUDIO_KINDS.union(*(s.kinds for s in STAGES))


def undrawn(
    items: Sequence[TypedEdlItem], sounds: Mapping[str, Path] | None = None
) -> list[str]:
    """Return why items cannot be drawn: kinds that no stage draws, the
    problems of the stages and SFX or music beds whose sound is not a
    bundled one or in sounds (library asset id -> file); empty when all of
    them can be."""
    problems = [
        f"item {item.id} ({item.kind}): the Pro Edit renderer does not draw "
        f"{item.kind} items"
        for item in items
        if item.kind not in DRAWN_KINDS
    ]
    for stage in STAGES:
        problems += stage.problems([i for i in items if i.kind in stage.kinds])
    return problems + sound_problems(items, sounds or {})


def video_chain(
    items: Sequence[TypedEdlItem],
    canvas: Canvas,
    stages: Sequence[Stage] = STAGES,
    cut: cutout.Cutout | None = None,
) -> str:
    """Return the filter chain that draws items on canvas, the clip's
    frames: PIXEL_FORMAT, then each stage's filters in stages order, with
    the subject cut-out cut (if any) around the overlay and caption
    stages."""
    filters = [PIXEL_FORMAT]
    for stage in stages:
        if stage.name == "overlay":
            filters += cutout.start_filters(cut, canvas.size, canvas.fps)
        filters += stage.filters([i for i in items if i.kind in stage.kinds], canvas)
        if stage.name == "captions":
            filters += cutout.end_filters(cut)
    return ",".join(filters)


def canvas_of(
    base: ProEditBase,
    items: Sequence[TypedEdlItem],
    size: tuple[int, int],
    fps: int,
) -> Canvas:
    """Return the canvas of the Pro Edit of base with items as size frames
    at fps: with the subject's face in each frame if a zoom, pan or
    face-anchored overlay needs it, the tracked object if an
    object-anchored overlay does (face_path.subject_faces) and, for
    anchored overlays, the zoom stage's cameras."""
    anchors = {i.params.anchor for i in items if isinstance(i, OverlayItem)}
    zooms = any(item.kind in motion.MOTION_KINDS for item in items)
    faces = subject_faces(base, fps, items) if zooms or "face" in anchors else []
    objects = (
        subject_faces(base, fps, items, tracked_object) if "object" in anchors else []
    )
    canvas = Canvas(fps, size, tuple(faces), tuple(objects))
    if anchors - {"screen"}:
        cameras = motion.cameras_of(items, canvas)
        canvas = replace(canvas, cameras=motion_time.shaken(cameras, items, canvas))
    return canvas


def proedit_graph(
    base: ProEditBase,
    items: Sequence[TypedEdlItem],
    size: tuple[int, int],
    fps: int,
    *,
    dialogue: bool = False,
    master: str = "",
    caption_files: Mapping[int, Path] | None = None,
    cut: cutout.Cutout | None = None,
) -> str:
    """Return the -filter_complex graph of the Pro Edit of base with items
    (validated, all drawn: undrawn), as size (width, height) frames at fps:
    the video in PRO_VIDEO, the sound in PRO_AUDIO (through the dialogue
    chain if dialogue and the master filters if set). The base is read from
    input 0 (its source from base.start); caption_files are the ASS files
    of the caption_style items by id (captions.caption_files); cut is the
    subject cut-out (cutout_pass.prepare_cutout), if any."""
    canvas = replace(
        canvas_of(base, items, size, fps), captions=dict(caption_files or {})
    )
    sound = _sound(base, items, fps, dialogue, master)
    chain = video_chain(items, canvas, cut=cut)
    return f"{framed_graph(base, size, fps)};{VIDEO_OUT}{chain}{PRO_VIDEO};{sound}"


def framed_graph(base: ProEditBase, size: tuple[int, int], fps: int) -> str:
    """Return the graph that frames and cuts base (render_graph.clip_graph)
    into VIDEO_OUT and AUDIO_OUT, as size frames at fps."""
    return clip_graph(
        base.plan,
        base.layout,
        base.start,
        size,
        fps,
        spans=base.cuts(fps),
        audio=base.censor or NO_AUDIO_FILTER,
        scenes=base.scenes,
        audio_spans=base.audio_cuts(fps),
    )


def proedit_audio_graph(
    base: ProEditBase,
    items: Sequence[TypedEdlItem],
    fps: int,
    *,
    dialogue: bool = False,
    master: str = "",
) -> str:
    """Return the -filter_complex graph of the sound alone of proedit_graph
    (the same filters; no video), cut and censored as the base is, in
    PRO_AUDIO."""
    spans = base.audio_cuts(fps) or base.cuts(fps)
    framed = audio_graph(spans, base.censor or NO_AUDIO_FILTER)
    return f"{framed};{_sound(base, items, fps, dialogue, master)}"


def _sound(
    base: ProEditBase,
    items: Sequence[TypedEdlItem],
    fps: int,
    dialogue: bool,
    master: str,
) -> str:
    """Return the sound_graph of items over the base's AUDIO_OUT."""
    return sound_graph(
        items,
        base.speech,
        base.sounds,
        AUDIO_OUT,
        PRO_AUDIO,
        dialogue=dialogue,
        master=master,
        loop=loop_end.loop_sound(items, fps),
    )
