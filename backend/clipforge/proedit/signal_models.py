"""The compact signals of a clip that the Pro Edit Director reads (SPEC-v3 3.2).

Every time is in seconds of the rendered clip (proedit/clock); every box is a
fraction (0..1) of the source frame. The object is what the LLM Director gets
as JSON, so it stays small: faces are sampled twice a second, the motion
energy once a second.
"""

from typing import Literal

from pydantic import BaseModel, Field

from clipforge.models import UnitInterval

# The non-speech events a Pro Edit plan reacts to.
EventKind = Literal["laugh", "applause", "cheer", "energy_peak"]
ReactionKind = Literal["laugh", "applause", "cheer"]


class WordSignal(BaseModel):
    """A caption word: emphasis is the effective emphasis (the clip's
    emphasis words and the AI/user marks), emoji the one a mark gave it."""

    text: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    speaker: str
    emphasis: bool
    emoji: str | None = None


class EventSignal(BaseModel):
    """A laugh, applause, cheer or energy peak (loudness peak)."""

    kind: EventKind
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    intensity: UnitInterval


class Punchline(BaseModel):
    """The word that a reaction answers: the word span (start, end) of the
    last word said before the reaction that starts at `at`."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    at: float = Field(ge=0)
    kind: ReactionKind
    intensity: UnitInterval
    text: str


class SpeakerTurn(BaseModel):
    """A run of words of one speaker."""

    speaker: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)


class QuietSpan(BaseModel):
    """A stretch without sound (silence) or speech (pause)."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)


class Sentence(BaseModel):
    """A sentence of the captions."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)


class FaceSample(BaseModel):
    """A face box at t, as fractions of the frame's width and height."""

    t: float = Field(ge=0)
    x: float
    y: float
    width: float
    height: float


class FaceTrackSignal(BaseModel):
    """One face followed through the clip (pipeline/identity); subject_share
    is the share of its samples in which it is the subject the framing
    follows (the speaker, pipeline/speaker)."""

    track: int
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    subject_share: UnitInterval
    samples: list[FaceSample]


class MotionSample(BaseModel):
    """The motion energy (0..1, fraction of full scale) of a stretch."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    energy: UnitInterval


class MotionSpan(BaseModel):
    """A stretch of high motion; level is its mean energy over the highest
    energy of the clip (0..1)."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    level: UnitInterval


class ProEditSignals(BaseModel):
    """What the Director knows of clip clip_id, which lasts duration seconds
    at fps frames a second, cut from a width x height source."""

    clip_id: int
    duration: float = Field(gt=0)
    fps: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    words: list[WordSignal]
    events: list[EventSignal]
    punchlines: list[Punchline]
    scene_cuts: list[float]
    speaker_turns: list[SpeakerTurn]
    silences: list[QuietSpan]
    pauses: list[QuietSpan]
    sentences: list[Sentence]
    faces: list[FaceTrackSignal]
    motion: list[MotionSample]
    motion_spans: list[MotionSpan]
