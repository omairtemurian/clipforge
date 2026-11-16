"""The transcript a clip editor shows (SPEC 8.5): the words of the clip with
up to CONTEXT_S seconds of the source before and after it.

A word here is a caption word (caption_lines.word_groups): the Whisper words
of one piece of a segment's text joined, so "twenty" and "-five" show as
"twenty-five", with the start of its first and the end of its last word.
"""

from collections.abc import Iterator

from clipforge.models import Clip, Transcript, Word
from clipforge.pipeline.caption_lines import word_groups

# Seconds of source the editor shows around a clip by default.
CONTEXT_S = 30.0


def editor_words(transcript: Transcript) -> Iterator[Word]:
    """Yield the caption words of transcript, in order, as Words in seconds:
    their texts joined without spaces, the speaker of the first word and the
    lowest probability of them. Words without text are left out."""
    for group in word_groups(transcript):
        text = "".join(word.text.strip() for word in group)
        if text:
            yield Word(
                text=text,
                start=group[0].start,
                end=max(group[-1].end, group[0].start),
                speaker=group[0].speaker,
                prob=min(word.prob for word in group),
                approximate=any(word.approximate for word in group),
            )


def context_window(
    clip: Clip, duration: float, context: float = CONTEXT_S
) -> tuple[float, float]:
    """Return the span of the source from context seconds before clip's start
    to context seconds after its end, inside the video (a duration of 0 is
    not known: no upper end)."""
    end = clip.end + context
    if duration > 0:
        end = max(clip.end, min(duration, end))
    return max(0.0, clip.start - context), end


def clip_transcript(
    transcript: Transcript, clip: Clip, duration: float, context: float = CONTEXT_S
) -> list[Word]:
    """Return the editor words of transcript that start in clip's context
    window (context_window), in order."""
    first, last = context_window(clip, duration, context)
    return [word for word in editor_words(transcript) if first <= word.start < last]
