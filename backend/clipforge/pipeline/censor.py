"""Auto censor of swear words (SPEC-v2 3.4).

A clip's caption_style.censor (CaptionCensor) turns it on: with auto, a
caption word whose key (caption_lines.word_key, any case) is on the default
list of the captions' language (assets/wordlists/censor_<code>.txt, always
with the English one) or on the custom list ({data_dir}/censor_words.json,
CensorWords) is censored; an entry ending in * matches the words that start
with it. A CaptionMark's censor overrides the lists for its word: True
censors it, False never does, also when the clip has no CaptionCensor.

A censored word's caption text is masked: its first letter stays and its
other letters and digits become * ("Fuck," -> "F***,"). Its sound, from
PAD_S before the word to PAD_S after it, is muted (volume 0) or replaced by
a BEEP_HZ sine (aeval), as the CaptionCensor's mode says (beep without one);
both filters are timeline-enabled only inside the censored windows.
"""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from clipforge import config
from clipforge.config import Settings
from clipforge.models import CaptionCensor, CensorMode, CensorWords
from clipforge.pipeline.caption_lines import CaptionWord, word_key
from clipforge.pipeline.step import StepError, write_text

WORDLISTS_DIR = Path(__file__).resolve().parents[3] / "assets" / "wordlists"
CENSOR_FILE = "censor_words.json"
# The language whose default list every language's captions also use.
BASE_LANGUAGE = "en"
# The sound of a censored word starts this early and ends this late.
PAD_S = 0.05
BEEP_HZ = 1000
# The beep's peak, of full scale: about -13.5 dBFS RMS.
BEEP_AMPLITUDE = 0.3

logger = logging.getLogger(__name__)

# A censored stretch of a rendered clip: (start, end) seconds from its start.
Window = tuple[float, float]


@dataclass(frozen=True)
class Matcher:
    """The entries of censor lists: whole words and prefixes, in lowercase."""

    words: frozenset[str]
    prefixes: tuple[str, ...]

    def matches(self, text: str) -> bool:
        """Return whether the caption word text is on the lists."""
        key = word_key(text).casefold()
        return bool(key) and (key in self.words or key.startswith(self.prefixes))


def compile_entries(entries: Iterable[str]) -> Matcher:
    """Return the Matcher of list entries ("word" or "prefix*")."""
    cleaned = [entry.strip().casefold() for entry in entries if entry.strip()]
    return Matcher(
        frozenset(entry for entry in cleaned if not entry.endswith("*")),
        tuple(entry[:-1] for entry in cleaned if entry.endswith("*") and entry[:-1]),
    )


@lru_cache(maxsize=16)
def default_entries(language: str, directory: Path = WORDLISTS_DIR) -> tuple[str, ...]:
    """Return the entries of the default lists of language: its own list in
    directory, if there is one, and the English one."""
    entries: list[str] = []
    for code in dict.fromkeys((BASE_LANGUAGE, language)):
        path = directory / f"censor_{code}.txt"
        if path.is_file():
            lines = path.read_text(encoding="utf-8").splitlines()
            entries += [line for line in lines if line.strip() and line[0] != "#"]
    return tuple(entries)


def censor_path(cfg: Settings | None = None) -> Path:
    """Return the custom censor list file of the data directory of cfg
    (default: the settings in use)."""
    return (config.settings if cfg is None else cfg).data_dir / CENSOR_FILE


def load_custom(cfg: Settings | None = None) -> CensorWords:
    """Return the saved custom censor list, or an empty one if none is
    saved. Raises StepError if the file is not a valid list."""
    path = censor_path(cfg)
    try:
        return CensorWords.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return CensorWords()
    except (ValidationError, OSError, UnicodeDecodeError) as exc:
        raise StepError(f"{path} is not a valid censor list: {exc}") from exc


def save_custom(words: CensorWords, cfg: Settings | None = None) -> None:
    """Save words as the custom censor list, replacing the saved one."""
    path = censor_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, words.model_dump_json(indent=2) + "\n")


def load_matcher(language: str, cfg: Settings | None = None) -> Matcher:
    """Return the Matcher of the default lists of language and the custom
    list. Raises StepError if the custom list's file is not valid."""
    return compile_entries((*default_entries(language), *load_custom(cfg).words))


def needs_lists(words: Iterable[CaptionWord], censor: CaptionCensor | None) -> bool:
    """Return whether censoring words takes the censor lists: auto censor
    is on and not every word has a mark that decides."""
    auto = censor is not None and censor.auto
    return auto and any(word.censor is None for word in words)


def is_censored(
    word: CaptionWord, censor: CaptionCensor | None, matcher: Matcher | None
) -> bool:
    """Return whether word is censored: its mark says so, or, without a
    mark that decides, auto censor is on and matcher matches it."""
    if word.censor is not None:
        return word.censor
    auto = censor is not None and censor.auto
    return auto and matcher is not None and matcher.matches(word.text)


def mask(text: str) -> str:
    """Return text with the letters and digits after its first one as *:
    "Fuck," -> "F***,", "'shit'" -> "'s***'"."""
    seen = False
    masked = []
    for char in text:
        if char.isalnum():
            masked.append(char if not seen else "*")
            seen = True
        else:
            masked.append(char)
    return "".join(masked)


def mask_words(
    words: Sequence[CaptionWord], censor: CaptionCensor | None, language: str
) -> list[CaptionWord]:
    """Return words with the text of the censored ones masked (is_censored,
    with the lists of language when they are needed)."""
    matcher = load_matcher(language) if needs_lists(words, censor) else None
    return [
        replace(word, text=mask(word.text))
        if is_censored(word, censor, matcher)
        else word
        for word in words
    ]


def censor_windows(
    words: Sequence[CaptionWord], censor: CaptionCensor | None, language: str
) -> list[Window]:
    """Return the windows of sound to censor for words (in milliseconds of
    the rendered clip): each censored word from PAD_S before it to PAD_S
    after it, in seconds to the millisecond, overlapping ones merged."""
    matcher = load_matcher(language) if needs_lists(words, censor) else None
    spans = sorted(
        (
            round(max(word.start / 1000 - PAD_S, 0.0), 3),
            round(word.end / 1000 + PAD_S, 3),
        )
        for word in words
        if is_censored(word, censor, matcher)
    )
    merged: list[Window] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def censor_filter(windows: Sequence[Window], mode: CensorMode) -> str:
    """Return the audio filter that censors windows of a clip's sound (t
    from its start): volume 0 for "mute", a BEEP_HZ sine for "beep"; "" if
    there are no windows."""
    if not windows:
        return ""
    enable = "+".join(f"between(t,{start:.3f},{end:.3f})" for start, end in windows)
    if mode == "mute":
        return f"volume=volume=0:enable='{enable}'"
    beep = f"{BEEP_AMPLITUDE}*sin(2*PI*{BEEP_HZ}*t)"
    return f"aeval=exprs={beep}:c=same:enable='{enable}'"
