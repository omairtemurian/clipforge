"""Builds the Pro Edit signals of a clip (SPEC-v3 3.2) from what the pipeline
already stored in the clip's job directory, in seconds of the rendered clip.

Read as stored: the transcript with the clip's emphasis words, caption
overrides and marks (pipeline/caption_lines, caption_emphasis), signals.json
(laughs, applause, cheers, energy peaks, silences, scene cuts), the speaker of
each word, and the pauses that speech cleanup finds (pipeline/cleanup).
Computed only for what is missing for the clip's span: its faces (the job's
face cache) and, if motion.json does not cover it, its motion
(proedit/signal_faces). No pipeline module changes. The music's beat grid is
not part of these signals (it belongs to the chosen asset).
"""

import re
from collections.abc import Iterable, Sequence
from contextlib import ExitStack
from itertools import groupby
from pathlib import Path
from typing import get_args

from clipforge import config
from clipforge.config import Settings
from clipforge.models import (
    CleanupOptions,
    Clip,
    SignalEvent,
    SignalList,
    Transcript,
)
from clipforge.pipeline.caption_lines import CaptionWord, clip_words, mark_emphasis
from clipforge.pipeline.cleanup import section_items
from clipforge.pipeline.faces import DetectFaces
from clipforge.pipeline.reframe import ClipSpan, speech_spans
from clipforge.pipeline.sections import played_words
from clipforge.pipeline.step import SIGNALS, TRANSCRIPT, StepError, load_json, load_meta
from clipforge.proedit.clock import ClipClock
from clipforge.proedit.signal_faces import face_signals, lazy_detector, motion_signals
from clipforge.proedit.signal_models import (
    EventKind,
    EventSignal,
    ProEditSignals,
    Punchline,
    QuietSpan,
    ReactionKind,
    Sentence,
    SpeakerTurn,
    WordSignal,
)
from clipforge.proedit.snap import PlanTiming

EVENT_KINDS: dict[str, EventKind] = {kind: kind for kind in get_args(EventKind)}
REACTION_KINDS: dict[str, ReactionKind] = {
    kind: kind for kind in get_args(ReactionKind)
}
# A punchline word ends at most this long before its reaction starts, or this
# long after (the laugh may be detected a little early).
PUNCHLINE_REACH_S = 1.5
PUNCHLINE_SLACK_S = 0.3
SENTENCE_END = re.compile(r"[.!?…][\"'”’)\]]*$")
# Speech cleanup's pauses, without its fillers.
PAUSES_ONLY = CleanupOptions(fillers=False, pauses=True)


def build_signals(
    work: Path,
    clip: Clip,
    *,
    cfg: Settings | None = None,
    detect: DetectFaces | None = None,
) -> ProEditSignals:
    """Return the signals of clip, the clip of the project whose job
    directory is work.

    cfg (default: the app settings) gives the render's frame rate and the
    face models; detect, if given, finds the faces of the frames that the
    job's face cache lacks instead of them. Raises StepError if the job's
    meta.json, transcript.json or signals.json is missing or not valid, the
    clip has no render time, or the face models cannot be loaded.
    """
    cfg = config.settings if cfg is None else cfg
    meta = load_meta(work)
    transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    events = load_json(work / SIGNALS, SignalList, "signals").root
    fps = cfg.render.fps
    clock = ClipClock(clip, fps)
    if clock.duration <= 0:
        raise StepError(f"clip {clip.id} plays nothing: its cuts remove all of it")
    caption_words = clip_words(
        transcript,
        clip.start,
        clip.end,
        clip.caption_overrides,
        clip.caption_style.word_marks or [],
    )
    words = played_words(mark_emphasis(caption_words, clip.emphasis_words), clip, fps)
    cut_times = [e.start for e in events if e.kind == "scene_cut"]
    cuts = [at for t in cut_times if (at := clock.point(t)) not in (None, 0.0)]
    reactions = reaction_signals(events, clock)
    with ExitStack() as stack:
        detector = detect or stack.enter_context(lazy_detector(cfg))
        faces = face_signals(
            work,
            clip,
            clock,
            meta,
            cut_times,
            speech_spans(work, ClipSpan(clip.id, clip.start, clip.end)),
            detector,
        )
    motion, motion_spans = motion_signals(work, clip, clock)
    pauses = [
        item
        for item in section_items(transcript, events, clip, PAUSES_ONLY)
        if item.kind == "pause"
    ]
    return ProEditSignals(
        clip_id=clip.id,
        duration=clock.duration,
        fps=fps,
        width=meta.width,
        height=meta.height,
        words=[word_signal(word) for word in words],
        events=reactions,
        punchlines=punchlines(reactions, words),
        scene_cuts=cuts,
        speaker_turns=speaker_turns(words),
        silences=quiet_spans(
            clock, ((e.start, e.end) for e in events if e.kind == "silence")
        ),
        pauses=quiet_spans(clock, ((p.start, p.end) for p in pauses)),
        sentences=sentences(words),
        faces=faces,
        motion=motion,
        motion_spans=motion_spans,
    )


def word_signal(word: CaptionWord) -> WordSignal:
    """Return word (milliseconds of the clip) as a signal in seconds."""
    return WordSignal(
        text=word.text.strip(),
        start=word.start / 1000,
        end=word.end / 1000,
        speaker=word.speaker,
        emphasis=word.emphasis,
        emoji=word.emoji or None,
    )


def reaction_signals(
    events: Iterable[SignalEvent], clock: ClipClock
) -> list[EventSignal]:
    """Return the laughs, applause, cheers and energy peaks of events that the
    clip plays, in clip time by start; an event that a cut splits becomes
    one per played part."""
    found = [
        EventSignal(kind=kind, start=start, end=end, intensity=event.intensity)
        for event in events
        if (kind := EVENT_KINDS.get(event.kind))
        for start, end in clock.spans(event.start, event.end)
    ]
    return sorted(found, key=lambda e: (e.start, e.kind))


def punchlines(
    reactions: Sequence[EventSignal], words: Sequence[CaptionWord]
) -> list[Punchline]:
    """Return the punchline of each laugh, applause and cheer in reactions:
    the last of words (milliseconds of the clip) that ends no more than
    PUNCHLINE_SLACK_S after the reaction starts nor PUNCHLINE_REACH_S before
    it; a word that two reactions answer is one punchline, of the first."""
    found: dict[tuple[float, float], Punchline] = {}
    for reaction in reactions:
        kind = REACTION_KINDS.get(reaction.kind)
        if kind is None:
            continue
        said = [
            word
            for word in words
            if word.end / 1000 <= reaction.start + PUNCHLINE_SLACK_S
            and reaction.start - word.end / 1000 <= PUNCHLINE_REACH_S
        ]
        if not said:
            continue
        word = said[-1]
        key = (word.start / 1000, word.end / 1000)
        found.setdefault(
            key,
            Punchline(
                start=key[0],
                end=key[1],
                at=reaction.start,
                kind=kind,
                intensity=reaction.intensity,
                text=word.text.strip(),
            ),
        )
    return sorted(found.values(), key=lambda p: p.start)


def speaker_turns(words: Sequence[CaptionWord]) -> list[SpeakerTurn]:
    """Return the runs of words of one speaker, in order."""
    return [
        SpeakerTurn(
            speaker=speaker,
            start=run[0].start / 1000,
            end=run[-1].end / 1000,
        )
        for speaker, group in groupby(words, key=lambda w: w.speaker)
        if (run := list(group))
    ]


def sentences(words: Sequence[CaptionWord]) -> list[Sentence]:
    """Return the sentences of words: runs that end at a word ending in . ! ?
    or …; the words left at the end make a last one."""
    found: list[Sentence] = []
    first = 0
    for index, word in enumerate(words):
        last = index == len(words) - 1
        if SENTENCE_END.search(word.text.strip()) or last:
            found.append(Sentence(start=words[first].start / 1000, end=word.end / 1000))
            first = index + 1
    return found


def quiet_spans(
    clock: ClipClock, spans: Iterable[tuple[float, float]]
) -> list[QuietSpan]:
    """Return the played parts of spans, (start, end) source seconds, in clip
    time, in order."""
    found = [
        QuietSpan(start=start, end=end)
        for source_start, source_end in spans
        for start, end in clock.spans(source_start, source_end)
    ]
    return sorted(found, key=lambda s: (s.start, s.end))


def plan_timing(signals: ProEditSignals, beats: Sequence[float] = ()) -> PlanTiming:
    """Return what the EDL post-processing snaps to for signals: the frame
    rate and duration, the word starts, the music beats (clip seconds) and
    the punchline word spans."""
    return PlanTiming(
        fps=signals.fps,
        duration=signals.duration,
        word_starts=tuple(word.start for word in signals.words),
        beats=tuple(beats),
        punchlines=tuple((p.start, p.end) for p in signals.punchlines),
    )
