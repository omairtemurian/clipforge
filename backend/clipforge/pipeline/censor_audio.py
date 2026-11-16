"""The censor filter of a clip's sound (SPEC-v2 3.4, pipeline/censor).

The words a clip censors are found among what its sound says
(polish.spoken_words: the transcript's words, not a translation's, at their
times after the clip's cuts), so render_clip runs the filter after the cuts.
"""

from pathlib import Path

from clipforge.models import Clip, Transcript
from clipforge.pipeline.censor import censor_filter, censor_windows
from clipforge.pipeline.polish import spoken_words
from clipforge.pipeline.step import TRANSCRIPT, load_json


def clip_censor_filter(work: Path, clip: Clip, fps: int) -> str:
    """Return the audio filter that beeps or mutes the words clip censors,
    for its render at fps frames a second from work, the work directory of
    its process job ("" if it censors none). Raises StepError if
    transcript.json is missing or not valid, or the custom censor list is
    needed and its file is not valid."""
    transcript = load_json(work / TRANSCRIPT, Transcript, "transcribe")
    censor = clip.caption_style.censor
    words = spoken_words(transcript, clip, fps)
    windows = censor_windows(words, censor, transcript.language)
    return censor_filter(windows, censor.mode if censor else "beep")
