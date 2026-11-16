"""What an installed optional engine must do (SPEC-v2 2.3, 5).

Every engine of `clipforge.engines.ENGINES` has a pytest marker
`engine_<name>` (registered in pyproject.toml). `missing_reason` is the
engine's own `install_check`: conftest skips an `engine_*` test with that
reason only when the engine is not installed, so a broken install fails the
test. `VERIFY` really uses each engine once. `make check-engines` runs the
marked tests.
"""

import importlib
import subprocess
from collections.abc import Callable
from pathlib import Path

from clipforge import config
from clipforge.engines import ENGINES, Engine
from clipforge.engines.deepfilternet import deep_filter_binary, deep_filter_version
from clipforge.engines.tts import kokoro_voices, piper_voices
from clipforge.engines.vlm_ollama import OllamaVisionEngine

BINARY_TIMEOUT_S = 30.0


def engine_for_marker(marker: str) -> Engine | None:
    """The engine whose pytest marker is `marker`, if any."""
    for engine in ENGINES.values():
        if engine.marker == marker:
            return engine
    return None


def missing_reason(marker: str) -> str | None:
    """Why the engine of this marker is not installed (None if it is, or if
    the marker is not an engine marker). Never cached: a test run is one look."""
    engine = engine_for_marker(marker)
    if engine is None:
        return None
    return engine.install_check().error


def _import(module: str) -> Callable[[], None]:
    def verify() -> None:
        importlib.import_module(module)

    return verify


def _run(binary: str, flag: str) -> Callable[[], None]:
    def verify() -> None:
        subprocess.run(
            [binary, flag], check=True, capture_output=True, timeout=BINARY_TIMEOUT_S
        )

    return verify


def _ollama_verify() -> None:
    assert OllamaVisionEngine("ollama_vlm", "x").install_check().installed


def _deepfilternet_verify() -> None:
    binary = deep_filter_binary()
    assert binary is not None
    deep_filter_version(binary)


def _kokoro_verify() -> None:
    assert kokoro_voices()


def _piper_verify() -> None:
    assert piper_voices()


def _segment_verify() -> None:
    import numpy as np
    from clipforge.proedit.segment import person_masker

    with person_masker(config.settings, 30) as mask:
        found = mask(np.zeros((64, 36, 3), dtype=np.uint8))
    assert found.shape == (64, 36)


def _yamnet_verify() -> None:
    from clipforge.pipeline.yamnet import load_yamnet

    load_yamnet(config.settings)


VERIFY: dict[str, Callable[[], None]] = {
    "engine_ollama_vlm": _ollama_verify,
    "engine_deepfilternet": _deepfilternet_verify,
    "engine_kokoro": _kokoro_verify,
    "engine_piper": _piper_verify,
    "engine_demucs": _import("demucs"),
    "engine_image_gen": _import("mflux"),
    "engine_realesrgan": _run("realesrgan-ncnn-vulkan", "-h"),
    "engine_voice_clone": _import("TTS"),
    "engine_yamnet": _yamnet_verify,
    "engine_segment": _segment_verify,
    "engine_embeddings": _import("sentence_transformers"),
    "engine_claude_code": _run(config.settings.claude_code_bin, "--version"),
}


def repo_root() -> Path:
    """The repository root (pyproject.toml and the Makefile live there)."""
    return Path(__file__).resolve().parents[2]
