"""The MediaPipe models that find reframe's subjects in a frame (SPEC 6.8).

Through the MediaPipe Tasks API in IMAGE mode (mediapipe 0.10.33 has no
legacy `mp.solutions`), loaded from cfg.models_dir/face and never
downloaded here (scripts/download_models.py does that):

- BlazeFace full-range finds the faces, up to ~5 m from the camera;
- the face landmarker measures how open each of the MOUTH_FACES largest
  faces' mouths is, on a crop around the face scaled to CROP_SIZE pixels
  (its own detector would miss small faces in the whole frame);
- in a frame without faces, EfficientDet-Lite0 finds the people, so a
  performer far away or turned away is still followed.
"""

from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

import numpy as np
import numpy.typing as npt

from clipforge.config import Settings
from clipforge.model_files import (
    FACE_DETECTOR,
    FACE_LANDMARKER,
    PERSON_DETECTOR,
    face_model_path,
    missing_face_models,
)
from clipforge.models import FaceBox
from clipforge.pipeline.step import StepError

# Detections that score lower are not faces (MediaPipe's default).
MIN_FACE_SCORE = 0.5
# People who score lower are not counted.
MIN_PERSON_SCORE = 0.4
# The faces of a frame whose mouths are measured, largest first.
MOUTH_FACES = 4
# The crop around a face is CROP_MARGIN face sizes on each side of its center.
CROP_MARGIN = 1.5
CROP_SIZE = 256
# Face mesh landmarks: inner upper and lower lip, forehead top and chin.
UPPER_LIP, LOWER_LIP, FOREHEAD, CHIN = 13, 14, 10, 152

Frame = npt.NDArray[np.uint8]
# Returns the faces (or else people) in an RGB frame, in the frame's pixels,
# largest first.
DetectFaces = Callable[[Frame], list[FaceBox]]


@contextmanager
def face_detector(cfg: Settings) -> Iterator[DetectFaces]:
    """Load the face models from cfg.models_dir/face and yield a function
    that returns the faces in an RGB frame with their mouths, or the people
    if it has no faces, largest first.

    The models are closed when the block ends. Raises StepError if a model
    is not downloaded or cannot be loaded.
    """
    missing = missing_face_models(cfg)
    if missing:
        raise StepError(
            f"the face model is not downloaded: {missing[0]} is missing; "
            "run `uv run python scripts/download_models.py`"
        )
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    def options(model: Any) -> Any:
        return BaseOptions(model_asset_path=str(face_model_path(cfg, model)))

    image = vision.RunningMode.IMAGE
    with ExitStack() as stack:
        try:
            faces = vision.FaceDetector.create_from_options(
                vision.FaceDetectorOptions(
                    base_options=options(FACE_DETECTOR),
                    running_mode=image,
                    min_detection_confidence=MIN_FACE_SCORE,
                )
            )
            stack.enter_context(faces)
            marks = vision.FaceLandmarker.create_from_options(
                vision.FaceLandmarkerOptions(
                    base_options=options(FACE_LANDMARKER),
                    running_mode=image,
                    num_faces=1,
                    min_face_detection_confidence=0.3,
                )
            )
            stack.enter_context(marks)
            people = vision.ObjectDetector.create_from_options(
                vision.ObjectDetectorOptions(
                    base_options=options(PERSON_DETECTOR),
                    running_mode=image,
                    score_threshold=MIN_PERSON_SCORE,
                    category_allowlist=["person"],
                )
            )
            stack.enter_context(people)
        except Exception as exc:  # the C library's errors subclass only Exception
            raise StepError(
                f"cannot load the face model from {cfg.models_dir / 'face'}: {exc}; "
                "download it again with "
                "`uv run python scripts/download_models.py --force`"
            ) from exc

        def to_image(frame: Frame) -> Any:
            data = np.ascontiguousarray(frame)
            return mp.Image(image_format=mp.ImageFormat.SRGB, data=data)

        def mouth(frame: Frame, face: FaceBox) -> float | None:
            found = marks.detect(to_image(face_crop(frame, face))).face_landmarks
            return mouth_opening(found[0]) if found else None

        def detect(frame: Frame) -> list[FaceBox]:
            found = [_box(d) for d in faces.detect(to_image(frame)).detections]
            if not found:
                seen = people.detect(to_image(frame)).detections
                return _largest_first([_box(d, "person") for d in seen])
            found = _largest_first(found)
            return [
                face.model_copy(update={"mouth": mouth(frame, face)})
                if k < MOUTH_FACES
                else face
                for k, face in enumerate(found)
            ]

        yield detect


def face_crop(frame: Frame, face: FaceBox) -> Frame:
    """Return the square of frame around face, CROP_MARGIN face sizes on
    each side of its center (cut at the frame's edges), scaled to CROP_SIZE
    pixels square."""
    import cv2

    height, width = frame.shape[:2]
    size = max(face.width, face.height) * CROP_MARGIN
    center_x, center_y = face.x + face.width / 2, face.y + face.height / 2
    left, right = max(0, int(center_x - size)), min(width, int(center_x + size))
    top, bottom = max(0, int(center_y - size)), min(height, int(center_y + size))
    if right <= left or bottom <= top:
        return np.zeros((CROP_SIZE, CROP_SIZE, 3), dtype=np.uint8)
    crop = frame[top:bottom, left:right]
    return np.asarray(cv2.resize(crop, (CROP_SIZE, CROP_SIZE)), dtype=np.uint8)


def mouth_opening(landmarks: Any) -> float | None:
    """Return the gap between the inner lips over the face's height (forehead
    to chin) of a face mesh's landmarks, to 0.001; None for a flat face."""
    face = abs(landmarks[CHIN].y - landmarks[FOREHEAD].y)
    if face <= 0:
        return None
    gap = abs(landmarks[LOWER_LIP].y - landmarks[UPPER_LIP].y)
    return round(float(gap / face), 3)


def _box(detection: Any, kind: str = "face") -> FaceBox:
    """Return a MediaPipe Detection as a FaceBox of kind, in the frame's
    pixels."""
    box = detection.bounding_box
    score = max((c.score or 0.0 for c in detection.categories), default=0.0)
    return FaceBox(
        x=float(box.origin_x),
        y=float(box.origin_y),
        width=float(box.width),
        height=float(box.height),
        score=round(float(score), 3),
        kind="person" if kind == "person" else "face",
    )


def _largest_first(boxes: list[FaceBox]) -> list[FaceBox]:
    """Return boxes sorted by area, largest first."""
    return sorted(boxes, key=lambda box: box.width * box.height, reverse=True)
