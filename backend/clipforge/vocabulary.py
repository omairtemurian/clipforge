"""The brand vocabulary (SPEC-v2 3.4), kept in {data_dir}/vocabulary.json.

Its terms go to Whisper as hotwords (hotwords_text) and its corrections are
applied to every transcript after transcription (pipeline/transcribe, with
pipeline/transcript_correct). replace_everywhere changes words in a whole
project: its transcript and every clip.
"""

import logging
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session, select

from clipforge import config
from clipforge.config import Settings
from clipforge.db import ClipRow
from clipforge.models import ReplaceResult, Transcript, Vocabulary, Word
from clipforge.pipeline.step import TRANSCRIPT, load_json, write_json, write_text
from clipforge.pipeline.transcript_correct import (
    correct_transcript,
    correct_word,
    replace_text,
)
from clipforge.search.fts import index_quietly

VOCABULARY_FILE = "vocabulary.json"
# Whisper reads at most 223 tokens of hotwords (faster-whisper cuts the rest
# off); about 4 characters per token of English leaves room under that.
HOTWORDS_MAX_CHARS = 600

logger = logging.getLogger(__name__)


class VocabularyError(RuntimeError):
    """The vocabulary file cannot be read."""


def vocabulary_path(cfg: Settings | None = None) -> Path:
    """Return the vocabulary file of the data directory of cfg (default:
    the settings in use)."""
    return (config.settings if cfg is None else cfg).data_dir / VOCABULARY_FILE


def load_vocabulary(cfg: Settings | None = None) -> Vocabulary:
    """Return the saved vocabulary, or an empty one if none is saved. Raises
    VocabularyError if the file is not a valid vocabulary."""
    path = vocabulary_path(cfg)
    try:
        return Vocabulary.model_validate_json(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Vocabulary()
    except (ValidationError, OSError, UnicodeDecodeError) as exc:
        raise VocabularyError(f"{path} is not a valid vocabulary: {exc}") from exc


def save_vocabulary(vocabulary: Vocabulary, cfg: Settings | None = None) -> None:
    """Save vocabulary, replacing the saved one."""
    path = vocabulary_path(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, vocabulary.model_dump_json(indent=2) + "\n")


def hotwords_text(vocabulary: Vocabulary) -> str | None:
    """Return the terms as Whisper's hotwords, "Kubernetes, OpenAI", whole
    terms up to HOTWORDS_MAX_CHARS; None if there are no terms."""
    text = ""
    for term in vocabulary.terms:
        joined = f"{text}, {term}" if text else term
        if len(joined) > HOTWORDS_MAX_CHARS:
            logger.warning("vocabulary: hotwords cut before %r (too long)", term)
            break
        text = joined
    return text or None


def replace_everywhere(
    engine: Engine,
    project_id: int,
    work: Path | None,
    heard: str,
    correct: str,
) -> ReplaceResult:
    """Change the whole words heard (any case) into correct in project
    project_id: in the transcript.json of its work directory (if work has
    one) and in every clip of the project, of every result set: title, hook
    text, description, reason, hashtags, emphasis words and, when heard is
    one word, the text of the caption words the editor changed."""
    matches = 0
    if work is not None and (work / TRANSCRIPT).is_file():
        transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
        fixed, matches = correct_transcript(transcript, {heard: correct})
        if matches:
            write_json(work / TRANSCRIPT, fixed)
            index_quietly(engine, project_id, work)
    changed = 0
    with Session(engine) as session:
        rows = session.exec(select(ClipRow).where(ClipRow.project_id == project_id))
        for row in rows:
            if _correct_clip(row, heard, correct):
                session.add(row)
                changed += 1
        session.commit()
    return ReplaceResult(transcript_matches=matches, clips_changed=changed)


def _correct_clip(row: ClipRow, heard: str, correct: str) -> bool:
    """Apply the change to the texts of row; return whether any changed."""
    changed = False
    for name in ("title", "hook_text", "description", "reason"):
        text, count = replace_text(getattr(row, name), heard, correct)
        if count:
            setattr(row, name, text)
            changed = True
    emphasis = [replace_text(text, heard, correct)[0] for text in row.emphasis_words]
    if emphasis != row.emphasis_words:
        row.emphasis_words = emphasis
        changed = True
    squash = "".join(heard.split()).casefold()
    hashtags = [
        "".join(correct.split()) if tag.casefold() == squash else tag
        for tag in row.hashtags
    ]
    if hashtags != row.hashtags:
        row.hashtags = hashtags
        changed = True
    overrides: list[Word] = []
    for word in row.caption_overrides:
        spelled = correct_word(word.text, heard, correct)
        if spelled is not None:
            word = word.model_copy(update={"text": spelled})
        overrides.append(word)
    if overrides != row.caption_overrides:
        row.caption_overrides = overrides
        changed = True
    return changed
