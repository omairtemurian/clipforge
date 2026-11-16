"""The ML models ClipForge downloads, and where they are kept.

Models live in cfg.models_dir (models/ in the project, ignored by git; SPEC
0.8): a faster-whisper model in models/whisper/<name>, YAMNet (ONNX) in
models/yamnet and the MediaPipe face, face landmark and person models in
models/face. whisper and YAMNet come from the Hugging Face Hub, whose own
files (HF_HOME: metadata, caches) are kept in models/huggingface, so a
download writes nothing outside the project; the MediaPipe models come from
Google's MediaPipe model storage.
"""

import hashlib
import logging
import os
from pathlib import Path
from typing import NamedTuple

import httpx

from clipforge.config import Settings

WHISPER_DIRNAME = "whisper"
HF_HOME_DIRNAME = "huggingface"
# The files of a CTranslate2 Whisper model, as faster_whisper.download_model
# fetches them; not every model has a vocabulary.* file.
WHISPER_PATTERNS = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]
# Without tokenizer.json, WhisperModel would fetch a tokenizer from the Hub.
WHISPER_REQUIRED = ("config.json", "model.bin", "tokenizer.json")
YAMNET_DIRNAME = "yamnet"
# Google's YAMNet (TF-Hub google/yamnet/1, Apache-2.0) converted to ONNX, at a
# fixed commit; each file must have this sha256 (docs/decisions.md).
YAMNET_REPO_ID = "audiomagic/yamnet-onnx"
YAMNET_REVISION = "f25b741c2f0bdc6d7e6db24b5fddda23347dbafd"
YAMNET_ONNX = "yamnet.onnx"
YAMNET_CLASS_MAP = "yamnet_class_map.csv"
YAMNET_SHA256 = {
    YAMNET_ONNX: "d3835ffbbd4a1bb3e777f0ca217b5007907f5171dd5d17c4236b95b2af8f908e",
    YAMNET_CLASS_MAP: (
        "cdf24d193e196d9e95912a2667051ae203e92a2ba09449218ccb40ef787c6df2"
    ),
}
FACE_DIRNAME = "face"


class ModelFile(NamedTuple):
    """A model file of MediaPipe's model storage, pinned by its sha256."""

    name: str
    url: str
    sha256: str


_MEDIAPIPE_MODELS = "https://storage.googleapis.com/mediapipe-models"
# The MediaPipe models reframe runs (Apache-2.0 per their model cards), at
# fixed versions (docs/decisions.md, TASK-22): BlazeFace full-range finds
# faces up to ~5 m away, the face landmarker measures mouths, and
# EfficientDet-Lite0 finds people whose faces are not seen.
FACE_DETECTOR = ModelFile(
    "blaze_face_full_range.tflite",
    f"{_MEDIAPIPE_MODELS}/face_detector/blaze_face_full_range/float16/1/"
    "blaze_face_full_range.tflite",
    "3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b",
)
FACE_LANDMARKER = ModelFile(
    "face_landmarker.task",
    f"{_MEDIAPIPE_MODELS}/face_landmarker/face_landmarker/float16/1/"
    "face_landmarker.task",
    "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
)
PERSON_DETECTOR = ModelFile(
    "efficientdet_lite0.tflite",
    f"{_MEDIAPIPE_MODELS}/object_detector/efficientdet_lite0/float32/1/"
    "efficientdet_lite0.tflite",
    "40338edf5ec70d43e318b0a716a84d4564cd1802759a7a07170c7e43796dbf58",
)
FACE_MODELS = (FACE_DETECTOR, FACE_LANDMARKER, PERSON_DETECTOR)
# Seconds; the largest model is 14 MB.
FACE_DOWNLOAD_TIMEOUT_S = 120.0

logger = logging.getLogger(__name__)


def whisper_model_dir(cfg: Settings) -> Path:
    """Return the directory that holds the whisper model cfg.whisper_model.

    The name is a faster-whisper model ("small") or a Hugging Face repo id
    ("Systran/faster-whisper-small", kept as "Systran--faster-whisper-small").
    """
    return cfg.models_dir / WHISPER_DIRNAME / cfg.whisper_model.replace("/", "--")


def missing_whisper_files(model_dir: Path) -> list[str]:
    """Return the names of the required model files that model_dir lacks."""
    return [name for name in WHISPER_REQUIRED if not (model_dir / name).is_file()]


def whisper_repo_id(name: str) -> str:
    """Return the Hugging Face repo of the faster-whisper model called name.

    name is one of faster_whisper.available_models() or a repo id containing
    "/", which is returned as it is. Raises ValueError for another name.
    """
    if "/" in name:
        return name
    from faster_whisper import available_models
    from faster_whisper.utils import _MODELS  # its model name -> repo table

    if name not in _MODELS:
        known = ", ".join(available_models())
        raise ValueError(f"unknown whisper model {name!r}; choose one of: {known}")
    return str(_MODELS[name])


def use_project_hf_home(cfg: Settings) -> Path:
    """Point HF_HOME at models_dir/huggingface, unless it is set, and return it.

    huggingface_hub reads HF_HOME when it is first imported (faster_whisper
    imports it too), so call this before importing either.
    """
    default = (cfg.models_dir / HF_HOME_DIRNAME).absolute()
    return Path(os.environ.setdefault("HF_HOME", str(default)))


def download_whisper_model(cfg: Settings, *, force: bool = False) -> Path:
    """Download the whisper model cfg.whisper_model and return its directory.

    Nothing is fetched if the model's files are there already, unless force.
    huggingface_hub shows progress bars on a terminal (not when output is
    redirected, or HF_HUB_DISABLE_PROGRESS_BARS is set). Raises ValueError
    for an unknown model name, huggingface_hub's errors if the download
    fails, and RuntimeError if the repo lacks a required file.
    """
    target = whisper_model_dir(cfg)
    if not force and not missing_whisper_files(target):
        logger.info("whisper model %r is in %s", cfg.whisper_model, target)
        return target
    use_project_hf_home(cfg)
    repo_id = whisper_repo_id(cfg.whisper_model)
    from huggingface_hub import snapshot_download

    logger.info("downloading whisper model %s into %s", repo_id, target)
    snapshot_download(
        repo_id,
        local_dir=target,
        allow_patterns=WHISPER_PATTERNS,
        force_download=force,
    )
    missing = missing_whisper_files(target)
    if missing:
        raise RuntimeError(
            f"{repo_id} has no {', '.join(missing)}: not a whisper model"
        )
    return target


def yamnet_model_dir(cfg: Settings) -> Path:
    """Return the directory that holds the YAMNet model and its class map."""
    return cfg.models_dir / YAMNET_DIRNAME


def missing_yamnet_files(model_dir: Path) -> list[str]:
    """Return the names of the YAMNet files that model_dir lacks."""
    return [name for name in YAMNET_SHA256 if not (model_dir / name).is_file()]


def download_yamnet_model(cfg: Settings, *, force: bool = False) -> Path:
    """Download YAMNet into models_dir/yamnet and return that directory.

    Nothing is fetched if its files are there already, unless force. Raises
    huggingface_hub's errors if the download fails, and RuntimeError if a
    file is missing or its sha256 is not the expected one; such a file is
    deleted, so it is never loaded.
    """
    target = yamnet_model_dir(cfg)
    if not force and not missing_yamnet_files(target):
        logger.info("YAMNet model is in %s", target)
        return target
    use_project_hf_home(cfg)
    from huggingface_hub import snapshot_download

    logger.info("downloading YAMNet model %s into %s", YAMNET_REPO_ID, target)
    snapshot_download(
        YAMNET_REPO_ID,
        revision=YAMNET_REVISION,
        local_dir=target,
        allow_patterns=list(YAMNET_SHA256),
        force_download=force,
    )
    wrong = []
    for name, expected in YAMNET_SHA256.items():
        path = target / name
        actual = file_sha256(path) if path.is_file() else "missing"
        if actual != expected:
            path.unlink(missing_ok=True)
            wrong.append(f"{name}: sha256 is {actual}, expected {expected}")
    if wrong:
        raise RuntimeError(f"{YAMNET_REPO_ID}@{YAMNET_REVISION} " + "; ".join(wrong))
    return target


def face_model_path(cfg: Settings, model: ModelFile = FACE_DETECTOR) -> Path:
    """Return the path of one of the FACE_MODELS (the face detector by
    default), in models_dir/face."""
    return cfg.models_dir / FACE_DIRNAME / model.name


def missing_face_models(cfg: Settings) -> list[Path]:
    """Return the paths of the FACE_MODELS that are not downloaded."""
    paths = [face_model_path(cfg, model) for model in FACE_MODELS]
    return [path for path in paths if not path.is_file()]


def download_face_model(
    cfg: Settings,
    *,
    force: bool = False,
    transport: httpx.BaseTransport | None = None,
) -> Path:
    """Download the FACE_MODELS into models_dir/face; return that directory.

    A model that is there already is not fetched again, unless force.
    transport, if given, carries the HTTP requests instead of the network
    (httpx.MockTransport in tests). Raises like download_model_file.
    """
    for model in FACE_MODELS:
        path = face_model_path(cfg, model)
        if not force and path.is_file():
            logger.info("%s is in %s", model.name, path.parent)
            continue
        download_model_file(model, path, transport)
    return cfg.models_dir / FACE_DIRNAME


def download_model_file(
    model: ModelFile, path: Path, transport: httpx.BaseTransport | None
) -> None:
    """Download model to path. The file is written next to path and only
    replaces it once its sha256 is model.sha256. Raises httpx.HTTPError if
    the download fails and RuntimeError if the file has another sha256;
    then nothing is left behind and a file that was there is kept."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.part")
    logger.info("downloading %s into %s", model.url, path.parent)
    try:
        with (
            httpx.Client(
                transport=transport,
                timeout=FACE_DOWNLOAD_TIMEOUT_S,
                follow_redirects=True,
            ) as client,
            client.stream("GET", model.url) as response,
        ):
            response.raise_for_status()
            with partial.open("wb") as file:
                for chunk in response.iter_bytes():
                    file.write(chunk)
        actual = file_sha256(partial)
        if actual != model.sha256:
            raise RuntimeError(
                f"{model.url}: sha256 is {actual}, expected {model.sha256}"
            )
        os.replace(partial, path)
    finally:
        partial.unlink(missing_ok=True)


def file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of the file at path, as hex."""
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()
