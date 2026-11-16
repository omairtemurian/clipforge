"""Tests of loading YAMNet and its class map (pipeline/yamnet).

The slow tests run the model that `make setup` downloads into models/yamnet;
they are skipped, saying so, when it is not there.
"""

import csv
from pathlib import Path

import numpy as np
import pytest
from clipforge.config import Settings
from clipforge.model_files import YAMNET_CLASS_MAP, YAMNET_ONNX, yamnet_model_dir
from clipforge.pipeline.step import StepError
from clipforge.pipeline.yamnet import Yamnet, frame_count, load_yamnet, read_class_map

HEADER = "index,mid,display_name\n"


def write_model_dir(cfg: Settings, class_map: str, onnx: Path | bytes) -> None:
    """Write a YAMNet model dir: class_map, and onnx's bytes or a link to it."""
    model_dir = yamnet_model_dir(cfg)
    model_dir.mkdir(parents=True)
    (model_dir / YAMNET_CLASS_MAP).write_text(class_map)
    if isinstance(onnx, Path):
        (model_dir / YAMNET_ONNX).symlink_to(onnx)
    else:
        (model_dir / YAMNET_ONNX).write_bytes(onnx)


def test_class_map_gives_the_class_names_in_index_order(tmp_path: Path) -> None:
    path = tmp_path / "map.csv"
    path.write_text(
        HEADER + '0,/m/09x0r,Speech\n1,/m/0ytgt,"Child speech, kid speaking"\n'
    )
    assert read_class_map(path) == ("Speech", "Child speech, kid speaking")


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("index,mid\n0,/m/09x0r\n", "'display_name'"),
        (HEADER + "zero,/m/09x0r,Speech\n", "invalid literal for int"),
        (HEADER + "1,/m/09x0r,Speech\n", "bad class rows"),
        (HEADER + "0,/m/09x0r\n", "bad class rows"),
        (HEADER, "bad class rows"),
        ("", "bad class rows"),
    ],
)
def test_other_files_are_not_class_maps(
    tmp_path: Path, content: str, error: str
) -> None:
    path = tmp_path / "map.csv"
    path.write_text(content)
    with pytest.raises(StepError, match=f"is not a YAMNet class map: .*{error}"):
        read_class_map(path)


def test_missing_model_is_an_error_that_says_how_to_download_it(
    tmp_path: Path,
) -> None:
    cfg = Settings(models_dir=tmp_path)
    with pytest.raises(StepError) as error:
        load_yamnet(cfg)
    assert str(error.value) == (
        f"the YAMNet model is not downloaded: {tmp_path / 'yamnet'} lacks "
        "yamnet.onnx, yamnet_class_map.csv; "
        "run `uv run python scripts/download_models.py`"
    )


def test_broken_model_is_an_error(tmp_path: Path) -> None:
    cfg = Settings(models_dir=tmp_path)
    write_model_dir(cfg, HEADER + "0,/m/09x0r,Speech\n", b"not a model")
    with pytest.raises(StepError, match="cannot load the YAMNet model from .*--force"):
        load_yamnet(cfg)


@pytest.mark.parametrize(
    ("samples", "frames"),
    [(0, 1), (15600, 1), (15601, 2), (23280, 2), (23281, 3), (38640, 4)],
)
def test_frames_start_every_7680_samples(samples: int, frames: int) -> None:
    assert frame_count(samples) == frames


@pytest.mark.slow
def test_class_indices_are_read_from_the_class_map(
    yamnet_cfg: Settings, yamnet_model: Yamnet
) -> None:
    path = yamnet_model_dir(yamnet_cfg) / YAMNET_CLASS_MAP
    with path.open(encoding="utf-8", newline="") as file:
        rows = {row["display_name"]: int(row["index"]) for row in csv.DictReader(file)}
    assert len(yamnet_model.class_names) == len(rows) == 521
    assert yamnet_model.class_index("Laughter") == rows["Laughter"] == 13
    assert yamnet_model.class_index("Applause") == rows["Applause"] == 62
    with pytest.raises(StepError, match="the YAMNet class map has no class 'Laugh'"):
        yamnet_model.class_index("Laugh")


@pytest.mark.slow
@pytest.mark.parametrize(
    ("samples", "frames"),
    # The model itself gives 5 frames for 38640 samples (see pipeline/yamnet).
    [(0, 1), (15600, 1), (15601, 2), (38640, 4), (7680 * 124 + 15600, 125)],
)
def test_scores_have_one_row_per_frame_and_one_column_per_class(
    yamnet_model: Yamnet, samples: int, frames: int
) -> None:
    scores = yamnet_model.scores(np.zeros(samples, dtype=np.float32))
    assert scores.shape == (frames, 521)
    assert scores.dtype == np.float32
    assert 0.0 <= scores.min() <= scores.max() <= 1.0


@pytest.mark.slow
def test_class_map_of_other_classes_is_an_error(
    yamnet_cfg: Settings, tmp_path: Path
) -> None:
    onnx = yamnet_model_dir(yamnet_cfg) / YAMNET_ONNX
    cfg = Settings(models_dir=tmp_path)
    write_model_dir(cfg, HEADER + "0,/m/1,a\n1,/m/2,b\n2,/m/3,c\n", onnx)
    with pytest.raises(StepError, match="is not YAMNet with the 3 classes of its"):
        load_yamnet(cfg)
