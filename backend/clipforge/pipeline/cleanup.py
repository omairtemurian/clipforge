"""Speech cleanup of a clip (SPEC-v2 3.5): what it would remove, for the
user to review, and the cut ranges of what they keep checked.

A preview (cleanup_preview) lists, in source order:

- fillers and pauses (polish.cleanup_suggestions) in each of the clip's
  sections: the filler words of the list of the chosen language
  (clipforge.fillers; default the transcript's) plus the user's extra
  ones, and the gaps longer than the pause threshold;
- bad takes, repeated or abandoned sentences (pipeline/bad_takes, found by
  the LLM), when asked for.

An item that the clip's cut ranges already remove whole is left out, so a
preview shows only what applying it changes. Applying (cleanup_cuts) cuts
the items the user left checked, merged with the clip's cut ranges and
kept inside its sections; the clip is then saved like any edit (versions,
undo). The items may overlap (a bad take over a pause): unchecking one
keeps only what no checked item removes.
"""

from collections.abc import Iterable, Sequence

from clipforge.fillers import NO_FILLERS, filler_words, list_language
from clipforge.models import (
    CleanupOptions,
    CleanupPreview,
    CleanupSuggestion,
    Clip,
    CutRange,
    SignalEvent,
    Transcript,
)
from clipforge.pipeline.auto_cut import merge_ranges
from clipforge.pipeline.caption_lines import to_ms
from clipforge.pipeline.polish import cleanup_suggestions
from clipforge.pipeline.sections import fit_cuts


def filler_language(transcript: Transcript, options: CleanupOptions) -> str:
    """Return the code of the filler list that options use for transcript:
    that of options.language, or of the transcript's language (a language
    without a list uses English, fillers.list_language)."""
    return list_language(options.language or transcript.language)


def section_items(
    transcript: Transcript,
    events: Iterable[SignalEvent],
    clip: Clip,
    options: CleanupOptions,
) -> list[CleanupSuggestion]:
    """Return the filler and pause cuts (polish.cleanup_suggestions) of each
    of clip's sections, as options ask for them, in play order; events are
    the job's signal events."""
    if options.fillers:
        language = filler_language(transcript, options)
        fillers = filler_words(language, options.extra_fillers)
    else:
        fillers = NO_FILLERS
    pause_ms = to_ms(options.pause_threshold_s) if options.pauses else None
    events = list(events)
    items: list[CleanupSuggestion] = []
    for start, end in clip.segments:
        items += cleanup_suggestions(transcript, events, start, end, fillers, pause_ms)
    return items


def is_applied(item: CleanupSuggestion, cut_ranges: Sequence[CutRange]) -> bool:
    """Return whether cut_ranges (merged) already remove item whole."""
    return any(
        start <= item.start and item.end <= end
        for start, end in merge_ranges(cut_ranges)
    )


def cleanup_preview(
    transcript: Transcript,
    events: Iterable[SignalEvent],
    clip: Clip,
    options: CleanupOptions,
    bad_takes: Iterable[CleanupSuggestion] = (),
) -> CleanupPreview:
    """Return what speech cleanup with options would remove from clip: its
    section_items and bad_takes (found by pipeline/bad_takes), in source
    order, without those its cut ranges already remove whole."""
    items = section_items(transcript, events, clip, options) + list(bad_takes)
    shown = [item for item in items if not is_applied(item, clip.cut_ranges)]
    return CleanupPreview(
        filler_language=filler_language(transcript, options),
        items=sorted(shown, key=lambda item: (item.start, item.end)),
    )


def checked_items(
    items: Sequence[CleanupSuggestion], unchecked: Iterable[int]
) -> list[CleanupSuggestion]:
    """Return the items whose index is not in unchecked, in order."""
    skipped = set(unchecked)
    return [item for index, item in enumerate(items) if index not in skipped]


def cleanup_cuts(
    clip: Clip, items: Sequence[CleanupSuggestion], unchecked: Iterable[int] = ()
) -> list[CutRange]:
    """Return clip's cut ranges after applying the checked items of a
    preview (checked_items): its cut ranges and theirs, merged
    (auto_cut.merge_ranges) and kept inside its sections (sections.fit_cuts),
    in order."""
    chosen = [(item.start, item.end) for item in checked_items(items, unchecked)]
    return fit_cuts(merge_ranges([*clip.cut_ranges, *chosen]), clip.segments)
