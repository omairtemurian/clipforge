"""The moments of a clip that the rule-based Director's rules react to
(SPEC-v3 3.5): each Trigger of a preset rule gives a list of Moments from the
clip's signals (SPEC-v3 3.2) and the music's beat grid, in clip seconds.

- hook: one moment in the first HOOK_S seconds: the first key word there,
  else the first word, else the clip start;
- emphasis: the key words (key_words) outside punchline words;
- punchline: each punchline word (strongest reaction first);
- setup: the build-up to each punchline, from the start of its sentence
  (at most SETUP_MAX_S before the word) to the word; shorter than
  SETUP_MIN_S is none;
- payoff: PAYOFF_S after each punchline word (the reaction);
- scene_cut, downbeat, beat: the scene cuts and the music's (down)beats;
- energy_peak: the loudness peaks.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from clipforge.proedit.director_music import MusicChoice
from clipforge.proedit.preset_defs import Trigger
from clipforge.proedit.signal_models import ProEditSignals, Punchline, WordSignal

HOOK_S = 2.0
SETUP_MIN_S = 1.0
SETUP_MAX_S = 4.0
PAYOFF_S = 0.8
KEY_WORD_MIN_LETTERS = 4
MomentSignal = Trigger | Literal["interrupt"]


@dataclass(frozen=True)
class Moment:
    """A moment of signal from t to end seconds (equal: an instant); what
    names it in reasons; word is the word it is about, if any."""

    signal: MomentSignal
    t: float
    end: float
    what: str
    word: WordSignal | None = None


def letters(text: str) -> str:
    """The letters and digits of a word (no punctuation)."""
    return re.sub(r"[^\w']", "", text)


def _in_punchline(word: WordSignal, punchlines: Sequence[Punchline]) -> bool:
    return any(p.start <= word.start < p.end for p in punchlines)


def key_words(signals: ProEditSignals) -> list[WordSignal]:
    """The words worth a move: the emphasis words; when the clip has none,
    the longest word (at least KEY_WORD_MIN_LETTERS letters, the first on a
    tie) of each sentence. Punchline words are left to the punchline rules."""
    words = [w for w in signals.words if not _in_punchline(w, signals.punchlines)]
    marked = [w for w in words if w.emphasis]
    if marked:
        return marked
    found: list[WordSignal] = []
    for sentence in signals.sentences:
        inside = [
            w
            for w in words
            if sentence.start <= w.start < sentence.end
            and len(letters(w.text)) >= KEY_WORD_MIN_LETTERS
        ]
        if inside:
            found.append(max(inside, key=lambda w: (len(letters(w.text)), -w.start)))
    return found


def _word_moment(signal: MomentSignal, word: WordSignal, label: str) -> Moment:
    return Moment(signal, word.start, word.end, f"the {label} '{word.text}'", word)


def _punchline_word(signals: ProEditSignals, p: Punchline) -> WordSignal | None:
    return next((w for w in signals.words if w.start == p.start), None)


def hook_moments(signals: ProEditSignals) -> list[Moment]:
    """The hook moment (module docstring)."""
    early = [w for w in key_words(signals) if w.start < HOOK_S]
    if early:
        return [_word_moment("hook", early[0], "hook word")]
    first = [w for w in signals.words if w.start < HOOK_S]
    if first:
        return [_word_moment("hook", first[0], "first word")]
    return [Moment("hook", 0.0, 0.0, "the clip start")]


def punchline_moments(signals: ProEditSignals) -> list[Moment]:
    """The punchline words, strongest reaction first (then time)."""
    ordered = sorted(signals.punchlines, key=lambda p: (-p.intensity, p.start))
    return [
        Moment(
            "punchline",
            p.start,
            p.end,
            f"the punchline '{p.text}' ({p.kind} after it)",
            _punchline_word(signals, p),
        )
        for p in ordered
    ]


def setup_moments(signals: ProEditSignals) -> list[Moment]:
    """The build-up to each punchline (module docstring)."""
    found: list[Moment] = []
    for p in signals.punchlines:
        starts = [s.start for s in signals.sentences if s.start <= p.start < s.end]
        start = max(starts[0] if starts else p.start, p.start - SETUP_MAX_S)
        if p.start - start >= SETUP_MIN_S:
            found.append(Moment("setup", start, p.start, f"the setup of '{p.text}'"))
    return found


def moments(
    signal: Trigger, signals: ProEditSignals, music: MusicChoice | None
) -> list[Moment]:
    """The moments of signal in the clip, in the order the rules use them."""
    duration = signals.duration
    if signal == "hook":
        return hook_moments(signals)
    if signal == "emphasis":
        return [_word_moment("emphasis", w, "key word") for w in key_words(signals)]
    if signal == "punchline":
        return punchline_moments(signals)
    if signal == "setup":
        return setup_moments(signals)
    if signal == "payoff":
        return [
            Moment(
                "payoff",
                p.end,
                min(p.end + PAYOFF_S, duration),
                f"the payoff of '{p.text}'",
            )
            for p in signals.punchlines
            if p.end < duration
        ]
    if signal == "scene_cut":
        return [
            Moment("scene_cut", t, t, f"the scene cut at {t:g} s")
            for t in signals.scene_cuts
        ]
    if signal == "energy_peak":
        return [
            Moment("energy_peak", e.start, e.end, f"the loudness peak at {e.start:g} s")
            for e in signals.events
            if e.kind == "energy_peak"
        ]
    if music is None:
        return []
    beats = music.downbeats(duration) if signal == "downbeat" else music.beats(duration)
    return [Moment(signal, t, t, f"the {signal} at {t:.2f} s") for t in beats]
