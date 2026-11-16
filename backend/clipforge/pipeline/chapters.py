"""Topic chapters (SPEC-v2 3.2): the LLM divides a project's transcript into
topics, and the user can clip by topic (reprompt.enqueue_reprompt with
ranges).

make_chapters cuts the sentences of the project's timeframe into parts of up
to CHAPTER_WINDOW_S seconds and asks the LLM for the chapters of each part
(prompts/chapters.md). A reply is checked (check_reply): it must be a valid
{"chapters": [...]} object whose chapters do not overlap and leave no
sentence outside them; otherwise it is sent back with what was wrong, up to
MAX_RETRIES times, and then the part fails. The valid chapters are snapped
onto sentences (snap_part): each starts at the start of the sentence nearest
to the time the LLM gave, the first of a part at the part's first sentence.
So all chapters together are contiguous: a chapter ends where the next one
starts, and the last one at the end of the last sentence. A topic that runs
over the border of two parts is split there. The chapters are saved as
chapters.json in the work directory.
"""

import json
import logging
from bisect import bisect_left
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError

from clipforge.config import Settings
from clipforge.llm import LLMClient, LLMError, create_client, reply_json
from clipforge.models import (
    Chapter,
    ChapterDraft,
    ChapterList,
    ChapterReply,
    Segment,
    Transcript,
)
from clipforge.pipeline.curate import MAX_RETRIES
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, describe_errors, fill
from clipforge.pipeline.enrich import timeframe_segments, timestamp
from clipforge.pipeline.step import (
    CHAPTERS,
    TRANSCRIPT,
    StepError,
    load_json,
    load_meta,
    write_json,
)

logger = logging.getLogger(__name__)

CHAPTERS_PROMPT = "chapters.md"
# The longest stretch of the transcript that one LLM request covers.
CHAPTER_WINDOW_S = 1800.0
# Prompt times are rounded to 0.1 s, so chapters may overlap, or end before a
# sentence starts, by this much.
TOLERANCE_S = 0.1
# Problems listed in a retry message; the rest are only counted.
MAX_PROBLEMS = 20


class ChapterLLMError(StepError):
    """The LLM cannot be reached, or sends no valid chapters."""


def sentences(segments: Sequence[Segment]) -> list[Segment]:
    """Return the segments that have text, in order: the sentences of the
    transcript."""
    return [segment for segment in segments if segment.text.strip()]


def split_parts(segments: Sequence[Segment]) -> list[list[Segment]]:
    """Cut sentences into parts that start at most CHAPTER_WINDOW_S seconds
    after the first sentence of the part, in order; a stretch without
    sentences gives no part."""
    parts: list[list[Segment]] = []
    first = 0.0
    for segment in segments:
        if not parts or segment.start - first >= CHAPTER_WINDOW_S:
            parts.append([])
            first = segment.start
        parts[-1].append(segment)
    return parts


def part_prompt(part: Sequence[Segment], problems: str | None = None) -> str:
    """Return the user message for a part: one "[mm:ss.s-mm:ss.s] S0: text"
    line per sentence, and, if the last reply was not valid, what was wrong
    with it and a request to reply again."""
    text = "\n".join(
        f"[{timestamp(s.start)}-{timestamp(s.end)}] {s.speaker}: "
        f"{' '.join(s.text.split())}"
        for s in part
    )
    if problems is None:
        return text
    return (
        f"{text}\n\nYour previous reply for this transcript was not valid:\n"
        f"{problems}\n\nReply again with only the JSON object "
        '{"chapters": [...]} described in the instructions.'
    )


def check_reply(drafts: Sequence[ChapterDraft], part: Sequence[Segment]) -> list[str]:
    """Return what is wrong with the chapters of a reply for a part, as
    "- ..." lines; none if it is valid.

    The chapters, taken in order of start, must each end after they start,
    must not overlap by more than TOLERANCE_S, and every sentence of the part
    must start in one of them. At most MAX_PROBLEMS are listed.
    """
    if not drafts:
        return ["- chapters: the reply has no chapters"]
    ordered = sorted(drafts, key=lambda c: c.start)
    problems = []
    for number, chapter in enumerate(ordered, start=1):
        if chapter.end <= chapter.start:
            problems.append(f"- chapter {number} ends before it starts")
        if number > 1 and chapter.start < ordered[number - 2].end - TOLERANCE_S:
            problems.append(
                f"- chapter {number} starts at {chapter.start:g}s, before "
                f"chapter {number - 1} ends at {ordered[number - 2].end:g}s"
            )
    for sentence in part:
        if not any(
            c.start - TOLERANCE_S <= sentence.start < c.end + TOLERANCE_S
            for c in ordered
        ):
            problems.append(f"- the sentence at {sentence.start:g}s is in no chapter")
    if len(problems) > MAX_PROBLEMS:
        problems[MAX_PROBLEMS:] = [f"- ... and {len(problems) - MAX_PROBLEMS} more"]
    return problems


def ask_part(
    llm: LLMClient, system: str, part: Sequence[Segment]
) -> list[ChapterDraft]:
    """Ask the LLM for the chapters of a part until a reply passes
    check_reply, at most MAX_RETRIES + 1 times.

    Raises ChapterLLMError if the LLM cannot be reached or refuses the
    request, or sends no valid reply.
    """
    problems = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            reply = llm.complete_json(system, part_prompt(part, problems))
        except LLMError as exc:
            raise ChapterLLMError(f"the LLM request failed: {exc}") from exc
        try:
            drafts = ChapterReply.model_validate_json(reply_json(reply)).chapters
        except ValidationError as exc:
            problems = describe_errors(exc)
        else:
            found = check_reply(drafts, part)
            if not found:
                return drafts
            problems = "\n".join(found)
        logger.warning(
            "chapters from %s: reply %d of %d is not valid:\n%s",
            timestamp(part[0].start),
            attempt,
            MAX_RETRIES + 1,
            problems,
        )
    raise ChapterLLMError(
        f"the LLM sent no valid chapters for the part from {timestamp(part[0].start)}"
    )


def snap_part(
    drafts: Sequence[ChapterDraft], part: Sequence[Segment]
) -> list[tuple[float, ChapterDraft]]:
    """Return (start, chapter) pairs of a part, in order, with each start the
    start of the sentence nearest to the chapter's start (the earlier one if
    two are as near) and the first one the part's first sentence.

    Of chapters that snap to one sentence the first is kept.
    """
    starts = [sentence.start for sentence in part]
    snapped: dict[float, ChapterDraft] = {}
    for draft in sorted(drafts, key=lambda c: c.start):
        at = bisect_left(starts, draft.start)
        near = [starts[i] for i in (at - 1, at) if 0 <= i < len(starts)]
        start = min(near, key=lambda s: (abs(s - draft.start), s))
        snapped.setdefault(start, draft)
    ordered = sorted(snapped.items())
    ordered[0] = (starts[0], ordered[0][1])
    return ordered


def make_chapters(
    work: Path, cfg: Settings, llm: LLMClient | None = None
) -> list[Chapter]:
    """Divide the transcript in work into topic chapters, save them as
    chapters.json there and return them, in order, numbered from 1.

    Asks llm, or the LLM of cfg, one part at a time (see the module
    docstring). Raises StepError if meta.json or transcript.json is missing
    or not valid or the timeframe has no speech, and its ChapterLLMError if
    an LLM request fails or sends no valid reply.
    """
    meta = load_meta(work)
    transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    spoken = sentences(timeframe_segments(transcript, meta))
    if not spoken:
        raise StepError("the transcript has no speech to divide into chapters")
    llm = llm if llm is not None else create_client(cfg)
    system = fill(
        PROMPTS_DIR / CHAPTERS_PROMPT,
        {"schema": json.dumps(ChapterDraft.model_json_schema(), indent=2)},
    )
    found: list[tuple[float, ChapterDraft]] = []
    for part in split_parts(spoken):
        logger.info("chapters of the part from %s", timestamp(part[0].start))
        found += snap_part(ask_part(llm, system, part), part)
    chapters = [
        Chapter(
            id=number,
            start=start,
            end=found[number][0] if number < len(found) else spoken[-1].end,
            title=" ".join(draft.title.split()),
            summary=" ".join(draft.summary.split()),
        )
        for number, (start, draft) in enumerate(found, start=1)
    ]
    write_json(work / CHAPTERS, ChapterList(chapters=chapters))
    logger.info("divided the transcript into %d chapters", len(chapters))
    return chapters


def read_chapters(work: Path) -> list[Chapter]:
    """Return the chapters in work's chapters.json; none if make_chapters has
    not run there. Raises StepError if the file is not valid."""
    if not (work / CHAPTERS).is_file():
        return []
    return load_json(work / CHAPTERS, ChapterList, "chapters").chapters


def chapter_ranges(
    chapters: Sequence[Chapter], ids: Sequence[int]
) -> list[tuple[float, float]]:
    """Return the (start, end) ranges of the chapters with ids, in order of
    time; chapters that follow each other are one range.

    Raises ValueError if an id is not a chapter's.
    """
    known = {chapter.id: chapter for chapter in chapters}
    missing = sorted(set(ids) - known.keys())
    if missing:
        raise ValueError(
            "no chapter " + ", ".join(str(i) for i in missing) + f" (1-{len(known)})"
        )
    ranges: list[tuple[float, float]] = []
    for chapter in sorted((known[i] for i in set(ids)), key=lambda c: c.start):
        if ranges and ranges[-1][1] == chapter.start:
            ranges[-1] = (ranges[-1][0], chapter.end)
        else:
            ranges.append((chapter.start, chapter.end))
    return ranges
