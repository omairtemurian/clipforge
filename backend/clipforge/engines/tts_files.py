"""The model files of the voiceover engines (engines/tts), pinned by sha256.

Kokoro: Kokoro-82M v1.0 (hexgrad, Apache-2.0) as ONNX and its voice styles,
from the kokoro-onnx release "model-files-v1.1" (the files its README
names; sha256 as GitHub lists them), in models/kokoro.

Piper: one voice ships by default, en_US-ljspeech-medium of
rhasspy/piper-voices (MIT; trained on the public domain LJ Speech dataset)
at a fixed commit, with its config and model card, in models/piper. Any
other Piper voice (<name>.onnx + <name>.onnx.json, MODEL_CARD optional as
<name>.MODEL_CARD) put there is listed too.
"""

import json
import re
from pathlib import Path
from typing import Any

import httpx

from clipforge.config import Settings
from clipforge.model_files import ModelFile, download_model_file

KOKORO_DIRNAME = "kokoro"
_KOKORO = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
)
KOKORO_MODEL = ModelFile(
    "kokoro-v1.0.onnx",
    f"{_KOKORO}kokoro-v1.0.onnx",
    "beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a",
)
KOKORO_VOICES = ModelFile(
    "voices-v1.0.bin",
    f"{_KOKORO}voices-v1.0.bin",
    "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
)
KOKORO_LICENSE = "Apache-2.0 (Kokoro-82M)"

PIPER_DIRNAME = "piper"
PIPER_CONFIG_SUFFIX = ".onnx.json"
PIPER_CARD_SUFFIX = ".MODEL_CARD"
PIPER_DEFAULT_VOICE = "en_US-ljspeech-medium"
_PIPER = (
    "https://huggingface.co/rhasspy/piper-voices/resolve/"
    "b4e358ffcb232591bf73a540e70f7de528e4174a/en/en_US/ljspeech/medium/"
)
PIPER_VOICE_FILES = (
    ModelFile(
        f"{PIPER_DEFAULT_VOICE}.onnx",
        f"{_PIPER}{PIPER_DEFAULT_VOICE}.onnx",
        "6f52a751e2349abe7a76735eb09dc1875298c77ea2342ffd2fef79ff81b87f22",
    ),
    ModelFile(
        f"{PIPER_DEFAULT_VOICE}{PIPER_CONFIG_SUFFIX}",
        f"{_PIPER}{PIPER_DEFAULT_VOICE}{PIPER_CONFIG_SUFFIX}",
        "141d612cc0a95ed7efc1ca936b845c2364967f2e9217c5dbfcf69fc4d6c65860",
    ),
    ModelFile(
        f"{PIPER_DEFAULT_VOICE}{PIPER_CARD_SUFFIX}",
        f"{_PIPER}MODEL_CARD",
        "fbee1529c89d36b3fe76d7e9f3f832dce17f44900a52d76a9bda735654766b4d",
    ),
)
UNKNOWN_LICENSE = "see the voice's model card"
_CARD_LICENSE = re.compile(r"^\*\s*License:\s*(.+?)\s*$", re.MULTILINE)


def kokoro_dir(cfg: Settings) -> Path:
    """Return where the Kokoro files are kept: models_dir/kokoro."""
    return cfg.models_dir / KOKORO_DIRNAME


def kokoro_paths(cfg: Settings) -> tuple[Path, Path]:
    """Return the Kokoro model file and voices file paths."""
    folder = kokoro_dir(cfg)
    return folder / KOKORO_MODEL.name, folder / KOKORO_VOICES.name


def missing_kokoro_files(cfg: Settings) -> list[str]:
    """Return the names of the Kokoro files that are not downloaded."""
    return [path.name for path in kokoro_paths(cfg) if not path.is_file()]


def piper_dir(cfg: Settings) -> Path:
    """Return where the Piper voices are kept: models_dir/piper."""
    return cfg.models_dir / PIPER_DIRNAME


def piper_models(cfg: Settings) -> list[Path]:
    """Return the Piper voice models (.onnx with their .onnx.json) in
    piper_dir, by name."""
    folder = piper_dir(cfg)
    if not folder.is_dir():
        return []
    return sorted(
        path
        for path in folder.glob("*.onnx")
        if path.with_name(f"{path.name}.json").is_file()
    )


def piper_license(model: Path) -> str:
    """Return the dataset license that the model card next to a Piper voice
    model gives, or UNKNOWN_LICENSE if it has none."""
    card = model.with_name(f"{model.stem}{PIPER_CARD_SUFFIX}")
    try:
        found = _CARD_LICENSE.search(card.read_text())
    except OSError:
        return UNKNOWN_LICENSE
    return found.group(1) if found else UNKNOWN_LICENSE


def piper_config(model: Path) -> dict[str, Any]:
    """Return the .onnx.json config of a Piper voice ({} if unreadable)."""
    try:
        info = json.loads(model.with_name(f"{model.name}.json").read_text())
    except (OSError, ValueError):
        return {}
    return info if isinstance(info, dict) else {}


def piper_language(model: Path, info: dict[str, Any]) -> str:
    """Return a Piper voice's language as a BCP 47 tag ("en_US" -> "en-US"):
    its config's language code, else the start of its file name."""
    code = (info.get("language") or {}).get("code") or model.stem.split("-")[0]
    return str(code).replace("_", "-")


def download_kokoro(
    cfg: Settings, *, force: bool = False, transport: httpx.BaseTransport | None = None
) -> Path:
    """Download the Kokoro model and voices (about 350 MB) into
    models_dir/kokoro and return it; files already there are kept unless
    force. Raises like model_files.download_model_file."""
    for model, path in zip(
        (KOKORO_MODEL, KOKORO_VOICES), kokoro_paths(cfg), strict=True
    ):
        if force or not path.is_file():
            download_model_file(model, path, transport)
    return kokoro_dir(cfg)


def download_piper_voice(
    cfg: Settings, *, force: bool = False, transport: httpx.BaseTransport | None = None
) -> Path:
    """Download the default Piper voice (about 64 MB) into models_dir/piper
    and return it; files already there are kept unless force. Raises like
    model_files.download_model_file."""
    folder = piper_dir(cfg)
    for model in PIPER_VOICE_FILES:
        path = folder / model.name
        if force or not path.is_file():
            download_model_file(model, path, transport)
    return folder
