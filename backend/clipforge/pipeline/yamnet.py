"""YAMNet (SPEC 6.3): AudioSet class scores for 0.96 s frames, one per 0.48 s.

The model is Google's YAMNet converted to ONNX, which
scripts/download_models.py puts in models/yamnet (see model_files); it runs
on the CPU with onnxruntime and never touches the network. Its input is a
16 kHz mono waveform with samples in [-1, 1]. Frame i reads samples
[7680 i, 7680 i + 15600): a 0.96 s patch of log-mel frames plus the end of
the last 25 ms STFT window. The model pads the waveform with zeros to a
whole number of frames, at least one: n samples give
1 + ceil((n - 15600) / 7680) frames (frame_count), except that some n for
which (n - 15600) / 7680 is a whole number give one more (38640 samples give
5 frames, not 4), as the graph computes it in float32 as
(n - 15600) * (1 / 7680). Yamnet.scores drops that extra frame, so the
frames of audio cut into chunks are those of the whole. Its scores are 0..1,
one per class and frame; the class names are those of the model's class map
file.
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from clipforge.config import Settings
from clipforge.model_files import (
    YAMNET_CLASS_MAP,
    YAMNET_ONNX,
    missing_yamnet_files,
    yamnet_model_dir,
)
from clipforge.pipeline.step import StepError

if TYPE_CHECKING:
    from onnxruntime import InferenceSession

SAMPLE_RATE = 16000
HOP_SAMPLES = 7680
WINDOW_SAMPLES = 15600
# The names of the model's input and of its scores output (the others are
# the embeddings and the log-mel spectrogram).
INPUT = "waveform"
SCORES = "output_0"
# CoreML, also available on macOS, would compile the model on each load.
PROVIDERS = ["CPUExecutionProvider"]

Waveform = npt.NDArray[np.float32]
Scores = npt.NDArray[np.float32]


@dataclass(frozen=True)
class Yamnet:
    """A loaded YAMNet: its onnxruntime session and its class names."""

    session: "InferenceSession"
    class_names: tuple[str, ...]

    def class_index(self, name: str) -> int:
        """Return the index of the class whose display name is name.

        Raises StepError if the class map has no such class.
        """
        try:
            return self.class_names.index(name)
        except ValueError:
            raise StepError(f"the YAMNet class map has no class {name!r}") from None

    def scores(self, waveform: Waveform) -> Scores:
        """Return the scores of waveform: one row per frame, one column per class.

        There are frame_count(len(waveform)) rows.
        """
        (scores,) = self.session.run([SCORES], {INPUT: waveform})
        return np.asarray(scores, dtype=np.float32)[: frame_count(len(waveform))]


def frame_count(samples: int) -> int:
    """Return the number of YAMNet frames of a waveform of samples samples."""
    return 1 + max(0, -(-(samples - WINDOW_SAMPLES) // HOP_SAMPLES))


def read_class_map(path: Path) -> tuple[str, ...]:
    """Return the class names of a YAMNet class map file, in index order.

    The file is a CSV file with a header and the columns index, mid and
    display_name, one row per class. Raises StepError if it is not.
    """
    try:
        with path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        indexes = [int(row["index"]) for row in rows]
        names = tuple(row["display_name"] for row in rows)
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise StepError(f"{path} is not a YAMNet class map: {exc}") from exc
    if not rows or indexes != list(range(len(rows))) or None in names:
        raise StepError(f"{path} is not a YAMNet class map: bad class rows")
    return names


def load_yamnet(cfg: Settings) -> Yamnet:
    """Load YAMNet and its class map from cfg.models_dir/yamnet.

    The model is not downloaded here (scripts/download_models.py does that).
    Raises StepError if its files are missing or cannot be loaded, or if the
    model's input and outputs are not those of YAMNet with one score per
    class of the class map.
    """
    model_dir = yamnet_model_dir(cfg)
    missing = missing_yamnet_files(model_dir)
    if missing:
        raise StepError(
            f"the YAMNet model is not downloaded: {model_dir} lacks "
            f"{', '.join(missing)}; run `uv run python scripts/download_models.py`"
        )
    class_names = read_class_map(model_dir / YAMNET_CLASS_MAP)
    from onnxruntime import InferenceSession

    try:
        session = InferenceSession(str(model_dir / YAMNET_ONNX), providers=PROVIDERS)
    except Exception as exc:  # onnxruntime's load errors subclass only Exception
        raise StepError(
            f"cannot load the YAMNet model from {model_dir}: {exc}; download it "
            "again with `uv run python scripts/download_models.py --force`"
        ) from exc
    inputs = [node.name for node in session.get_inputs()]
    outputs = {node.name: node.shape for node in session.get_outputs()}
    if inputs != [INPUT] or outputs.get(SCORES, [])[-1:] != [len(class_names)]:
        raise StepError(
            f"{model_dir / YAMNET_ONNX} is not YAMNet with the "
            f"{len(class_names)} classes of its class map: inputs {inputs}, "
            f"outputs {outputs}"
        )
    return Yamnet(session, class_names)
