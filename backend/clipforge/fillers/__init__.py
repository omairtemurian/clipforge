"""Filler words by language (SPEC-v2 3.5 speech cleanup).

Each language with a list has a YAML file in this package named after its
Whisper code (languages.WHISPER_LANGUAGES): en.yaml holds English. A list
has two kinds of entries:

- always: hesitation sounds that are a filler wherever they are said
  ("um", "euh", "äh");
- alone: words that are a filler only when they stand alone between pauses
  (polish.is_filler), since they are real words too ("like", "este", "ну").

Entries and spoken words are compared by filler_key: the caption word key
(caption_lines.word_key) with every run of three or more of one character
squeezed to two, so "ummm" and "ummmmm" both match the entry "umm". A
language without a file uses the English list (FALLBACK_LANGUAGE), as
speech cleanup did before there were other lists.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from clipforge.captions_templates import read_yaml
from clipforge.pipeline.caption_lines import word_key

FILLERS_DIR = Path(__file__).resolve().parent
FALLBACK_LANGUAGE = "en"
# A run of three or more of one character.
_LONG_RUN = re.compile(r"(.)\1{2,}")


class FillerList(BaseModel):
    """The entries of one language's YAML file."""

    model_config = ConfigDict(extra="forbid")

    always: list[str] = Field(min_length=1)
    alone: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class FillerWords:
    """The filler keys (filler_key) of a language: always, fillers wherever
    they are said; alone, fillers only between pauses."""

    always: frozenset[str]
    alone: frozenset[str]


NO_FILLERS = FillerWords(frozenset(), frozenset())


def filler_key(text: str) -> str:
    """Return the key that filler entries and spoken words are compared by:
    word_key(text) with runs of three or more of one character squeezed to
    two ("Ummmm," -> "umm")."""
    return _LONG_RUN.sub(r"\1\1", word_key(text))


def filler_languages(directory: Path = FILLERS_DIR) -> list[str]:
    """Return the codes of the languages that have a filler list, sorted."""
    return sorted(path.stem for path in directory.glob("*.yaml"))


def list_language(language: str, directory: Path = FILLERS_DIR) -> str:
    """Return the code of the list that language uses: its own if it has
    one (the part of its code before "-" or "_", any case), else
    FALLBACK_LANGUAGE."""
    code = re.split(r"[-_]", language.strip().lower(), maxsplit=1)[0]
    return (
        code if code and (directory / f"{code}.yaml").is_file() else FALLBACK_LANGUAGE
    )


@lru_cache(maxsize=32)
def _load(code: str, directory: Path) -> FillerWords:
    """Return the filler keys of directory's list code.yaml; raises
    pydantic's ValidationError if it is not valid."""
    entries = FillerList.model_validate(read_yaml(directory / f"{code}.yaml"))
    return FillerWords(_keys(entries.always), _keys(entries.alone))


def filler_words(
    language: str, extra: Iterable[str] = (), directory: Path = FILLERS_DIR
) -> FillerWords:
    """Return the filler words of language (list_language's list), with the
    words of extra added as always-fillers."""
    words = _load(list_language(language, directory), directory)
    added = _keys(extra)
    if not added:
        return words
    return FillerWords(words.always | added, words.alone - added)


def _keys(entries: Iterable[str]) -> frozenset[str]:
    """Return the filler keys of entries, without empty ones."""
    return frozenset(key for key in map(filler_key, entries) if key)
