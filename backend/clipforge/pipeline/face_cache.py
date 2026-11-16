"""The faces found in a job's source, kept per source frame (steering:
faster reframe of long clips).

Reframe finds the faces of each clip in its own samples (pipeline/faces),
so clips that overlap, or a clip reframed again for another aspect or
preset, would search the same frames again. FaceCache keeps what the
detector found in each sampled frame by the frame's index in the source
(its time times the source's frame rate, rounded), in FACE_CACHE in the
job's work directory, for every later reframe of the job to reuse. A
cache made at another frame rate or analysis size is ignored.
"""

import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

from clipforge.models import FaceBox
from clipforge.pipeline.step import write_json

logger = logging.getLogger(__name__)

FACE_CACHE = "faces_cache.json"


class FaceCacheFile(BaseModel):
    """FACE_CACHE: the faces of each sampled source frame, by frame index,
    found at analysis size (width, height) in a source of fps frames a
    second."""

    fps: float
    analysis: tuple[int, int]
    frames: dict[int, list[FaceBox]] = {}


class FaceCache:
    """The faces found in the frames of a job's source (module docstring)."""

    def __init__(self, job_dir: Path, fps: float, analysis: tuple[int, int]) -> None:
        """Load the cache of job_dir, if it was made for a source of fps
        frames a second searched at analysis size; else start empty."""
        self.path = job_dir / FACE_CACHE
        self.data = FaceCacheFile(fps=fps, analysis=analysis)
        self.changed = False
        if not self.path.is_file():
            return
        try:
            stored = FaceCacheFile.model_validate_json(self.path.read_bytes())
        except (OSError, ValidationError) as exc:
            logger.warning("ignoring the face cache %s: %s", self.path, exc)
            return
        if stored.fps == fps and stored.analysis == analysis:
            self.data = stored

    def index(self, t: float) -> int:
        """Return the index of the source frame shown at t seconds."""
        return round(t * self.data.fps)

    def get(self, t: float) -> list[FaceBox] | None:
        """Return copies of the faces found in the frame at t seconds, or
        None if it was not searched yet."""
        found = self.data.frames.get(self.index(t))
        return None if found is None else [face.model_copy() for face in found]

    def put(self, t: float, faces: list[FaceBox]) -> None:
        """Keep faces as those found in the frame at t seconds."""
        self.data.frames[self.index(t)] = [face.model_copy() for face in faces]
        self.changed = True

    def __len__(self) -> int:
        return len(self.data.frames)

    def save(self) -> None:
        """Write the cache to the job's work directory if it changed."""
        if self.changed:
            write_json(self.path, self.data)
            self.changed = False
