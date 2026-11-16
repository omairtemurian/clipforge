"""What a Pro Edit render starts from (SPEC-v3 3.6): the clip's source video,
framed and cut as the clip's normal render frames and cuts it.

The base keeps the clip's framing (its crop plan as the editor set it,
layout and scenes), the parts of its segments that play less its cut
ranges (in whole frames, in play order: sections.played_spans, the time
the EDL speaks in) and its censor filter, so the words it beeps stay
beeped. Captions, timeline layers, zoom keyframes, the hook's punch-in and
the auto color of the normal render are not part of it: a Pro Edit draws
its own from its EDL. Its speech spans (the words the clip says, in the
rendered clip's time) are where SFX and music beds duck (proedit/audio),
and sounds maps the library asset ids its SFX and music bed items may play
to their files (proedit/audio/sounds.library_sounds). Its source words
(every word of the transcript in the clip, cut or not, in seconds from its
start) keep the J and L cuts of its cuts off words (proedit/pacing.py).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from clipforge.models import Clip, CropPlan, CutRange, Layout, SourceSpan, Transcript
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.censor_audio import clip_censor_filter
from clipforge.pipeline.framing import framed_plan
from clipforge.pipeline.polish import rendered_words, spoken_words
from clipforge.pipeline.scene_framing import scene_parts
from clipforge.pipeline.scene_graph import ScenePart
from clipforge.pipeline.sections import played_spans
from clipforge.pipeline.step import SOURCE, TRANSCRIPT, load_json
from clipforge.proedit.pacing import jl_spans

Span = tuple[float, float]


@dataclass(frozen=True)
class ProEditBase:
    """source from start to end seconds, framed in layout with plan (or
    scene by scene as scenes say), playing segments (none: one from start
    to end) without cut_ranges; censor is the audio filter of its censored
    words and speech the (start, end) seconds of its words, both in the
    rendered clip's time ("" and () if none); sounds maps library asset
    ids to the sound files that SFX items may play. words are the caption
    words that kinetic caption items show (polish.rendered_words: in ms of
    the rendered clip, censored words masked) with the clip's
    emphasis_words and speaker_colors. source_words are the (start, end)
    seconds from start of every word of the source in it and jl_frames the
    most frames a J or L cut moves the sound at a cut (0: straight cuts;
    pacing.py)."""

    source: Path
    start: float
    end: float
    plan: CropPlan
    layout: Layout
    segments: Sequence[SourceSpan] = ()
    cut_ranges: Sequence[CutRange] = ()
    scenes: Sequence[ScenePart] = ()
    censor: str = ""
    speech: Sequence[Span] = ()
    sounds: Mapping[str, Path] = field(default_factory=dict)
    words: Sequence[CaptionWord] = ()
    emphasis_words: Sequence[str] = ()
    speaker_colors: Mapping[str, str] = field(default_factory=dict)
    source_words: Sequence[Span] = ()
    jl_frames: int = 0

    def played(self, fps: int) -> list[tuple[float, float]]:
        """Return the (start, end) seconds from start that the render plays,
        in play order (sections.played_spans at fps)."""
        sections = list(self.segments) or [(self.start, self.end)]
        return played_spans(self.start, self.end, sections, self.cut_ranges, fps)

    def cuts(self, fps: int) -> list[tuple[float, float]]:
        """Return the played spans when the render must cut (cut ranges or
        more than one segment), else [] (the whole span plays as it is)."""
        if self.cut_ranges or len(self.segments) > 1:
            return self.played(fps)
        return []

    def audio_cuts(self, fps: int) -> list[tuple[float, float]] | None:
        """Return the spans of sound that play with the cuts' picture
        spans with J and L cuts (pacing.jl_spans), None when the sound
        plays the picture's spans."""
        cuts = self.cuts(fps)
        length = self.end - self.start
        return jl_spans(cuts, self.source_words, length, fps, self.jl_frames)

    def duration(self, fps: int) -> float:
        """Return the length in seconds of the rendered clip."""
        return sum(end - start for start, end in self.played(fps))


def clip_base(
    work: Path, clip: Clip, fps: int, sounds: Mapping[str, Path] | None = None
) -> ProEditBase:
    """Return the base of a Pro Edit of clip from work, the work directory
    of its project's process job, for a render at fps, whose SFX and music
    beds may play
    the library sounds (asset id -> file). Raises StepError if the clip's
    crop plan, meta.json or transcript.json is missing or not valid."""
    plan = framed_plan(work, clip)
    transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    return ProEditBase(
        source=work / SOURCE,
        start=clip.start,
        end=clip.end,
        plan=plan,
        layout=clip.layout,
        segments=tuple(clip.segments),
        cut_ranges=tuple(clip.cut_ranges),
        scenes=tuple(scene_parts(work, clip, plan)),
        censor=clip_censor_filter(work, clip, fps),
        speech=tuple(
            (word.start / 1000, word.end / 1000)
            for word in spoken_words(transcript, clip, fps)
        ),
        sounds=dict(sounds or {}),
        words=tuple(rendered_words(transcript, clip, fps)),
        emphasis_words=tuple(clip.emphasis_words),
        speaker_colors=dict(clip.caption_style.speaker_colors or {}),
        source_words=tuple(
            (
                max(word.start, clip.start) - clip.start,
                min(word.end, clip.end) - clip.start,
            )
            for segment in transcript.segments
            for word in segment.words
            if word.end > clip.start and word.start < clip.end
        ),
    )
