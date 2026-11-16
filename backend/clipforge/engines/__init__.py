"""The registry of optional engines and their cached install checks
(SPEC-v2 2.3).

`engine_statuses()` is what the capability API serves and what a feature asks
before it runs: a check can call Ollama, so its result is kept until
`refresh=True` (or `clear_cache`). A new engine: add it to `ENGINES`, its
marker to pyproject.toml and the Makefile `ENGINE_MARKERS`, a `verify` to
tests/engine_probes.py and an "Engine: <name>" section to the README (see
`Engine.doc_anchor`).
"""

import threading

from clipforge.engines.base import Engine, EngineStatus, InstallStatus
from clipforge.engines.checks import (
    BinaryEngine,
    ClaudeCodeEngine,
    ModuleEngine,
    SegmentEngine,
    YamnetEngine,
)
from clipforge.engines.deepfilternet import DeepFilterNetEngine
from clipforge.engines.tts import KokoroEngine, PiperEngine
from clipforge.engines.vlm_ollama import OllamaVisionEngine

__all__ = [
    "ENGINES",
    "Engine",
    "EngineStatus",
    "InstallStatus",
    "clear_cache",
    "engine_statuses",
    "get_engine",
    "install_status",
    "is_installed",
]

ENGINES: dict[str, Engine] = {
    engine.name: engine
    for engine in (
        OllamaVisionEngine("ollama_vlm", "Vision model (Ollama)"),
        DeepFilterNetEngine("deepfilternet", "Speech enhancement (DeepFilterNet)"),
        KokoroEngine("kokoro", "Voiceover (Kokoro)"),
        PiperEngine("piper", "Voiceover (Piper)"),
        ModuleEngine("demucs", "Source separation", "demucs", "demucs"),
        ModuleEngine("image_gen", "AI image B-roll", "mflux", "mflux"),
        BinaryEngine("realesrgan", "AI upscaling", "realesrgan-ncnn-vulkan"),
        ModuleEngine("voice_clone", "Voice cloning", "TTS", "coqui-tts"),
        YamnetEngine("yamnet", "Audio events (YAMNet)"),
        SegmentEngine("segment", "Subject cut-out (MediaPipe)"),
        ModuleEngine(
            "embeddings",
            "Text embeddings",
            "sentence_transformers",
            "sentence-transformers",
        ),
        ClaudeCodeEngine("claude_code", "Claude subscription (Claude Code)"),
    )
}

_cache: dict[str, InstallStatus] = {}
_lock = threading.Lock()


def get_engine(name: str) -> Engine:
    """The engine called `name`; KeyError if there is none."""
    return ENGINES[name]


def clear_cache() -> None:
    """Forget every cached install check."""
    with _lock:
        _cache.clear()


def install_status(name: str, *, refresh: bool = False) -> InstallStatus:
    """The install check of an engine, cached until refresh."""
    engine = get_engine(name)
    with _lock:
        if refresh or name not in _cache:
            _cache[name] = engine.install_check()
        return _cache[name]


def is_installed(name: str, *, refresh: bool = False) -> bool:
    """Whether the engine is installed (the capability flag)."""
    return install_status(name, refresh=refresh).installed


def engine_statuses(*, refresh: bool = False) -> list[EngineStatus]:
    """Every engine with its capability flag, in registry order."""
    return [
        engine.status(install_status(name, refresh=refresh))
        for name, engine in ENGINES.items()
    ]
