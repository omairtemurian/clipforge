"""The six-word caption fixture shared by the caption tests: builders.SIX
("Wait, my brother ate the pizza.") written as a job's transcript, its
captions for a clip, and their Dialogue lines."""

from pathlib import Path

from builders import SIX
from clipforge.models import Aspect, Clip, Transcript
from clipforge.pipeline.captions import write_captions
from clipforge.pipeline.render import SIZES
from clipforge.pipeline.step import TRANSCRIPT, write_json

# The six words of builders.SIX: each word is active until the next one
# starts; "the" until its end, as a pause follows it.
TIMES = [
    ("00.00", "00.36"),
    ("00.36", "00.54"),
    ("00.54", "00.84"),
    ("00.84", "01.14"),
    ("01.14", "01.25"),
    ("01.70", "02.20"),
]


def write(job: Path, clip: Clip, aspect: Aspect = "9:16") -> str:
    """Write the six words' transcript into job and return clip's captions
    for a render in aspect."""
    write_json(job / TRANSCRIPT, Transcript(language="en", duration=60, segments=[SIX]))
    return write_captions(job, clip, SIZES[aspect], 30).read_text(encoding="utf-8")


def dialogues(ass: str) -> list[str]:
    """Return the Dialogue lines of an ASS file."""
    return [line for line in ass.splitlines() if line.startswith("Dialogue:")]


def caption_dialogues(hook: str, texts: list[str]) -> list[str]:
    """Return the Dialogue lines of the six words' captions: the hook, then
    a Caption event with each of texts at TIMES."""
    return [
        f"Dialogue: 1,0:00:00.00,0:00:02.50,Hook,,0,0,0,,{hook}",
        *(
            f"Dialogue: 0,0:00:{start},0:00:{end},Caption,,0,0,0,,{text}"
            for (start, end), text in zip(TIMES, texts, strict=True)
        ),
    ]
