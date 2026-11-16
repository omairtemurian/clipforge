"""What the stages of a Pro Edit render draw on (graph.STAGES): the rendered
clip's frames, their size and rate, the subject's face and the tracked
object in each of them (face_path.subject_faces), for the stages that keep
them in the picture or draw on them, and the camera of the frames that the
zoom stage moves, for the stages after it (overlay.py)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Box:
    """A box in a frame, as fractions (0..1) of its width (left, right) and
    height (top, bottom)."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        """Return the box's width, a fraction of the frame's."""
        return self.right - self.left

    @property
    def height(self) -> float:
        """Return the box's height, a fraction of the frame's."""
        return self.bottom - self.top

    @property
    def center(self) -> tuple[float, float]:
        """Return the box's center (x, y), as fractions of the frame."""
        return (self.left + self.right) / 2, (self.top + self.bottom) / 2


@dataclass(frozen=True)
class Camera:
    """What a frame shows: the window of 1 / scale of the frame's width and
    height (scale >= 1) centered at (x, y), fractions of the frame."""

    scale: float
    x: float
    y: float


@dataclass(frozen=True)
class Canvas:
    """size (width, height) frames at fps; faces[n] is the subject's face
    and objects[n] the tracked object (pipeline/object_tracking) in frame n
    before the zoom stage (None: none is known; frames past the end of the
    sequence have none); cameras[n] is the camera of frame n that the zoom
    stage draws (motion.py, motion_time.shaken; frames without one are not
    moved), filled in only for the stages after it that need it; captions
    maps a caption_style item's id to its ASS file (captions.py)."""

    fps: int
    size: tuple[int, int]
    faces: Sequence[Box | None] = ()
    objects: Sequence[Box | None] = ()
    cameras: Mapping[int, Camera] = field(default_factory=dict)
    captions: Mapping[int, Path] = field(default_factory=dict)

    def face(self, frame: int) -> Box | None:
        """Return the subject's face in frame, or None."""
        return self.faces[frame] if 0 <= frame < len(self.faces) else None

    def object(self, frame: int) -> Box | None:
        """Return the tracked object in frame, or None."""
        return self.objects[frame] if 0 <= frame < len(self.objects) else None
