"""Curate step (SPEC 6.5): ask the LLM for clip candidates, write candidates.json.

The lines of enriched.txt, the transcript of the project's timeframe with
its signal markers (SPEC 6.4, pipeline/enrich), are cut into windows of
chunk_minutes that overlap by chunk_overlap_s, and the LLM is asked for the
clips of each window with the prompt of the job's genre (pipeline/genre:
the chosen genre, or for "auto" comedy or podcast by the laughs). A reply
that is not a valid {"clips": [...]} object is sent back with its
validation errors up to MAX_RETRIES times; after that the window is skipped
and logged. The candidates of all windows are then checked, deduplicated
and capped (curate_select). With clipping "captions_only" the LLM is not asked:
the whole timeframe is the one candidate (whole_clip). With "keyword_search"
it is not asked either: the candidates are windows around the places the
search terms are said (pipeline/keyword_search), checked like the LLM's.
With clip anything, the timeline lines of what is seen and heard
(pipeline/visuals) go between the transcript lines.
"""

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from clipforge.candidate_rules import DEFAULT_HASHTAGS, longest_clip
from clipforge.config import Settings
from clipforge.llm import LLMClient, LLMError, create_client, reply_json
from clipforge.models import CandidateList, ClipCandidate, SourceMeta
from clipforge.pipeline.curate_prompt import (
    describe_errors,
    system_prompt,
    user_prompt,
)
from clipforge.pipeline.curate_select import llm_average, select_candidates
from clipforge.pipeline.enrich import PromptLine, parse_line, timestamp
from clipforge.pipeline.genre import job_genre
from clipforge.pipeline.keyword_search import search
from clipforge.pipeline.step import (
    CANDIDATES,
    ENRICHED,
    StepError,
    StepSettings,
    is_done,
    load_meta,
    load_text,
    write_json,
)
from clipforge.pipeline.transcript_merge import plan_chunks
from clipforge.pipeline.visuals import wanted, with_timeline

logger = logging.getLogger(__name__)

# Slightly more than the rounding of a prompt time (0.05 s, SPEC 6.4).
ROUNDING_S = 0.06
# Times a window is asked again after an invalid reply before it is skipped.
MAX_RETRIES = 2


@dataclass(frozen=True, slots=True)
class Window:
    """The transcript lines that start between start and end source seconds."""

    start: float
    end: float
    lines: list[PromptLine]

    def __str__(self) -> str:
        return f"{timestamp(self.start)}-{timestamp(self.end)}"


def read_enriched(path: Path) -> list[PromptLine]:
    """Return the lines of enriched.txt, which the enrich step writes.

    Blank lines are skipped. Raises StepError if the file is missing or a
    line does not start with "[mm:ss.s-".
    """
    lines = []
    for number, text in enumerate(load_text(path, "enrich").splitlines(), start=1):
        if not text.strip():
            continue
        try:
            lines.append(parse_line(text))
        except ValueError as exc:
            raise StepError(f"{path} line {number} is not valid: {exc}") from exc
    return lines


def plan_windows(
    lines: Sequence[PromptLine],
    start: float,
    end: float,
    cfg: Settings,
    longest: float = 0.0,
) -> list[Window]:
    """Cut the lines of the timeframe from start to end seconds into windows.

    Windows are cfg.chunk_minutes long and overlap by cfg.chunk_overlap_s,
    or for clips of up to longest seconds at least twice that long and
    overlapping by longest, so that each such clip fits in a window; a
    line goes into every window its start lies in. The lines are those of
    enriched.txt, which holds only the timeframe but rounds starts to 0.1 s,
    so the first window also takes the lines that start before it and the
    last window those that start after it. Raises StepError if the span or
    the chunk settings cannot be cut.
    """
    try:
        chunks = plan_chunks(
            start,
            end,
            max(cfg.chunk_minutes * 60, 2 * longest),
            max(cfg.chunk_overlap_s, longest),
        )
    except ValueError as exc:
        raise StepError(f"cannot cut the transcript into windows: {exc}") from exc
    windows = []
    for index, chunk in enumerate(chunks):
        low = -math.inf if index == 0 else chunk.start
        high = math.inf if index == len(chunks) - 1 else chunk.end
        held = [line for line in lines if low <= line.start < high]
        windows.append(Window(chunk.start, chunk.end, held))
    return windows


def plan_scopes(
    meta: SourceMeta,
    lines: Sequence[PromptLine],
    ranges: Sequence[tuple[float, float]],
) -> list[tuple[SourceMeta, list[PromptLine]]]:
    """Return the parts of the video that curate asks about apart, each as
    the meta whose timeframe it is and the lines of enriched.txt in it.

    Without ranges that is the whole timeframe with all lines. With ranges
    (clip by topic) it is each range cut to the timeframe, with the lines
    that start in it; a range outside the timeframe is left out. Lines
    start rounded to 0.1 s, so a line counts for the range its true start
    lies in.
    """
    if not ranges:
        return [(meta, list(lines))]
    scopes = []
    for start, end in sorted(ranges):
        start, end = max(start, meta.timeframe_start), min(end, meta.timeframe_end)
        if start >= end:
            continue
        held = [
            line
            for line in lines
            if start - ROUNDING_S <= line.start < end - ROUNDING_S
        ]
        scope = meta.model_copy(update={"timeframe_start": start, "timeframe_end": end})
        scopes.append((scope, held))
    return scopes


def parse_reply(reply: str) -> list[ClipCandidate]:
    """Return the clips of an LLM reply; raise ValidationError if it is invalid.

    A reply wrapped in a Markdown code block is unwrapped first.
    """
    return CandidateList.model_validate_json(reply_json(reply)).clips


def ask_window(
    llm: LLMClient, system: str, window: Window
) -> list[ClipCandidate] | None:
    """Ask the LLM for the clip candidates of a window.

    A window without lines is not sent and has no candidates. An invalid
    reply is sent back with its validation errors up to MAX_RETRIES times.
    Returns None, after logging, when no reply was valid. Raises StepError if
    the LLM cannot be reached or refuses the request.
    """
    if not window.lines:
        logger.info("window %s has no speech; not sent to the LLM", window)
        return []
    errors = None
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            reply = llm.complete_json(system, user_prompt(window.lines, errors))
        except LLMError as exc:
            raise StepError(f"the LLM request failed: {exc}") from exc
        try:
            return parse_reply(reply)
        except ValidationError as exc:
            errors = describe_errors(exc)
            logger.warning(
                "window %s: reply %d of %d is not valid:\n%s",
                window,
                attempt,
                MAX_RETRIES + 1,
                errors,
            )
    logger.warning("skipped window %s: the LLM sent no valid reply", window)
    return None


def whole_clip(meta: SourceMeta) -> ClipCandidate:
    """Return the one candidate of a job without clipping: its whole
    timeframe, titled after the video, with neutral scores and no hook."""
    return ClipCandidate(
        start=meta.timeframe_start,
        end=meta.timeframe_end,
        title=meta.title[:70] or "Full video",
        hook_text="",
        description="",
        hashtags=list(DEFAULT_HASHTAGS),
        emphasis_words=[],
        reason="Captions only: the whole video or timeframe.",
        hook=50,
        flow=50,
        value=50,
        trend=50,
    )


def run(job_dir: Path, settings: StepSettings, *, force: bool = False) -> Path:
    """Write the clip candidates of the job's transcript to candidates.json.

    Reads meta.json (ingest), enriched.txt (enrich) and, for the genre
    "auto" or clip anything, signals.json (signals), with clip anything
    motion.json and frame_captions.json (visuals), and asks settings.llm, or the LLM of
    settings.cfg, window by window with the prompt of the job's genre; a
    keyword search reads transcript.json instead and asks no LLM. Skips
    the work if candidates.json exists, unless force. Raises StepError if an
    input is missing or not valid, the windows cannot be planned, or an LLM
    request fails.
    """
    output = job_dir / CANDIDATES
    if is_done(output, force=force):
        logger.info("%s exists; skipping curate", output)
        settings.report_progress(1.0)
        return output
    output.unlink(missing_ok=True)

    meta = load_meta(job_dir)
    if settings.processing.clipping == "captions_only":
        write_json(output, CandidateList(clips=[whole_clip(meta)]))
        logger.info("captions only: the whole timeframe is one clip")
        settings.report_progress(1.0)
        return output
    if settings.processing.clipping == "keyword_search":
        found = search(job_dir, meta, settings.processing, settings.cfg)
        kept = select_candidates(found, meta, settings.processing, settings.cfg)
        write_json(output, CandidateList(clips=kept))
        logger.info("keyword search: kept %d of %d windows", len(kept), len(found))
        settings.report_progress(1.0)
        return output
    lines = read_enriched(job_dir / ENRICHED)
    if wanted(settings):
        lines = with_timeline(lines, job_dir, meta)
    genre = job_genre(job_dir, settings.processing, meta)
    cfg = settings.cfg
    longest = longest_clip(
        settings.processing.length_presets, cfg, settings.processing.custom_length
    )
    scopes = plan_scopes(meta, lines, settings.ranges)
    plans = [
        plan_windows(held, scope.timeframe_start, scope.timeframe_end, cfg, longest)
        for scope, held in scopes
    ]
    total = sum(len(windows) for windows in plans)
    llm = settings.llm if settings.llm is not None else create_client(cfg)
    system = system_prompt(genre, settings.processing, cfg)
    logger.info("asking for %s clips (genre %s)", genre, settings.processing.genre)

    proposed_count = skipped = done = 0
    chosen: list[ClipCandidate] = []
    for (scope, _), windows in zip(scopes, plans, strict=True):
        proposed: list[ClipCandidate] = []
        for window in windows:
            done += 1
            logger.info("curating window %d/%d (%s)", done, total, window)
            clips = ask_window(llm, system, window)
            if clips is None:
                skipped += 1
            else:
                proposed += clips
            settings.report_progress(done / total)
        proposed_count += len(proposed)
        chosen += select_candidates(proposed, scope, settings.processing, cfg)

    kept = sorted(chosen, key=llm_average, reverse=True)[: cfg.max_clips_from_llm]
    write_json(output, CandidateList(clips=kept))
    logger.log(
        logging.INFO if kept else logging.WARNING,
        "kept %d of %d clip candidates; %d of %d windows skipped",
        len(kept),
        proposed_count,
        skipped,
        total,
    )
    return output
