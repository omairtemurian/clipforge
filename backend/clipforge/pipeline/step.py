"""What every pipeline step shares (SPEC 6).

A step is a module clipforge.pipeline.<name> with a function
`run(job_dir, settings, *, force=False) -> Path`. It writes its outputs into
the job's work directory, returns the path of its main output, and skips the
work when that output already exists, unless force is set.

A stage of a job that has finished leaves a marker, steps/<name>.done in
the job's work directory (mark_done), written after all of its outputs: a
job that restarts after a crash or a kill skips the marked stages
(step_done) and resumes at the first one without a marker (SPEC-v2 2.2).
"""

import importlib
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from clipforge import config
from clipforge.config import Settings
from clipforge.models import ProcessingSettings, SourceMeta

if TYPE_CHECKING:
    from clipforge.llm import LLMClient

# The steps in pipeline order; each one is a module of this package.
STEP_NAMES = (
    "ingest",
    "transcribe",
    "signals",
    "visuals",
    "enrich",
    "curate",
    "score",
    "snap",
)
WORK_DIRNAME = "work"
# The files ingest writes into the job directory, which later steps read.
SOURCE = "source.mp4"
AUDIO = "audio.wav"
THUMB = "thumb.jpg"
META = "meta.json"
# What transcribe, signals, enrich, curate, score and snap write for the
# later steps.
TRANSCRIPT = "transcript.json"
SIGNALS = "signals.json"
AUDIO_EVENTS = "audio_events.json"
# What the visuals step writes for clip anything (pipeline/visuals).
FRAME_CAPTIONS = "frame_captions.json"
MOTION = "motion.json"
ENRICHED = "enriched.txt"
CANDIDATES = "candidates.json"
SCORED = "scored.json"
SNAPPED = "snapped.json"
# What the chapters endpoint writes next to them (pipeline/chapters).
CHAPTERS = "chapters.json"
# The directory of the job work directory that holds the stage markers.
MARKERS_DIRNAME = "steps"

M = TypeVar("M", bound=BaseModel)


class StepError(RuntimeError):
    """A step cannot finish for a reason the user can fix, such as a bad source."""


@dataclass(frozen=True)
class StepSettings:
    """The inputs of one step run.

    source is the project's video: an http(s) URL or a local file path.
    on_progress, if set, receives the step's progress as a fraction from 0 to 1.
    llm is the LLM that curate asks; None means the one cfg.llm_provider
    names (clipforge.llm.create_client).
    ranges, if not empty, are the (start, end) source-second ranges that
    curate is restricted to (clip by topic, pipeline/chapters): it asks for
    clips of each range apart and keeps only clips inside one.
    """

    source: str
    processing: ProcessingSettings = field(default_factory=ProcessingSettings)
    cfg: Settings = field(default_factory=lambda: config.settings)
    on_progress: Callable[[float], None] | None = None
    llm: "LLMClient | None" = None
    ranges: tuple[tuple[float, float], ...] = ()

    def report_progress(self, fraction: float) -> None:
        """Pass fraction, clamped to 0..1, to on_progress if it is set."""
        if self.on_progress is not None:
            self.on_progress(min(max(fraction, 0.0), 1.0))


class Step(Protocol):
    """The run function of a pipeline step."""

    def __call__(
        self, job_dir: Path, settings: StepSettings, *, force: bool = False
    ) -> Path: ...


def job_dir(job_id: int, cfg: Settings | None = None) -> Path:
    """Return the work directory of a job: {data_dir}/work/{job_id} (SPEC 3)."""
    data_dir = (config.settings if cfg is None else cfg).data_dir
    return data_dir / WORK_DIRNAME / str(job_id)


def is_done(output: Path, *, force: bool) -> bool:
    """Return True if a step may skip: its output exists and force is off."""
    return output.exists() and not force


def marker_path(job_dir: Path, name: str) -> Path:
    """Return the path of the marker of the stage called name in job_dir."""
    return job_dir / MARKERS_DIRNAME / f"{name}.done"


def mark_done(job_dir: Path, name: str) -> None:
    """Record that the stage called name of the job in job_dir finished.

    Call it after the stage has written all of its outputs: the marker is
    written in one step (write_text), so it never exists half written.
    """
    path = marker_path(job_dir, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text(path, f"{name}\n")


def step_done(job_dir: Path, name: str) -> bool:
    """Return True if the stage called name of the job in job_dir finished
    (its marker exists, mark_done)."""
    return marker_path(job_dir, name).is_file()


def done_steps(job_dir: Path) -> list[str]:
    """Return the names of the finished stages of the job in job_dir, sorted."""
    return sorted(path.stem for path in job_dir.glob(f"{MARKERS_DIRNAME}/*.done"))


def write_text(path: Path, text: str) -> None:
    """Write text to path as UTF-8, replacing path in one step.

    The text goes to path.tmp first and is then renamed, so a reader never
    sees half a file and an interrupted step leaves no output behind.
    """
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def write_json(path: Path, model: BaseModel) -> None:
    """Write model to path as indented JSON, replacing path in one step."""
    write_text(path, model.model_dump_json(indent=2) + "\n")


def missing_input(path: Path, step: str) -> StepError:
    """Return the error for an input file that step writes but has not."""
    return StepError(f"{path} not found; run the {step} step first")


def load_text(path: Path, step: str) -> str:
    """Return the UTF-8 text stored in path, which step writes.

    Raises StepError if the file is missing (step has not run for the job) or
    is not UTF-8 text.
    """
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise missing_input(path, step) from exc
    except UnicodeDecodeError as exc:
        raise StepError(f"{path} is not UTF-8 text: {exc}") from exc


def load_json(path: Path, model: type[M], step: str) -> M:
    """Return the model instance stored as JSON in path, which step writes.

    Raises StepError if the file is missing (step has not run for the job) or
    does not hold a valid model.
    """
    try:
        return model.model_validate_json(path.read_bytes())
    except FileNotFoundError as exc:
        raise missing_input(path, step) from exc
    except ValidationError as exc:
        raise StepError(f"{path} is not valid: {exc}") from exc


def load_meta(job_dir: Path) -> SourceMeta:
    """Return the SourceMeta that ingest wrote to job_dir/meta.json.

    Raises StepError if the file is missing (ingest has not run for the job)
    or is not a valid SourceMeta.
    """
    return load_json(job_dir / META, SourceMeta, "ingest")


def load_step(name: str) -> Step:
    """Return the run function of the step called name.

    Only the requested step's module is imported, so running one step does
    not load the libraries of the others. Raises ValueError for a name that
    is not in STEP_NAMES.
    """
    if name not in STEP_NAMES:
        choices = ", ".join(STEP_NAMES)
        raise ValueError(f"unknown step {name!r}; choose one of: {choices}")
    step: Step = importlib.import_module(f"clipforge.pipeline.{name}").run
    return step
