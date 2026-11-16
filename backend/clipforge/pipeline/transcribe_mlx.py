"""The MLX Whisper backend of the transcribe step: Whisper on the Apple GPU.

faster-whisper (CTranslate2) only uses the CPU on a Mac. mlx-whisper runs the
same OpenAI Whisper weights, converted to MLX, on Apple Silicon's GPU. This
module chooses between the two (choose_backend), finds and downloads the MLX
model (models/whisper-mlx/<name>), and runs a chunk of audio through it,
returning the same TimedWord list that faster-whisper's output becomes, so the
chunk merge and the Transcript model are shared.
"""

import importlib.util
import logging
import platform
import sys
import wave
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Literal

import numpy as np
import numpy.typing as npt

from clipforge.config import Settings
from clipforge.model_files import use_project_hf_home
from clipforge.pipeline.step import StepError
from clipforge.pipeline.transcript_merge import TimedWord

Backend = Literal["faster_whisper", "mlx"]

MLX_DIRNAME = "whisper-mlx"
MLX_REQUIRED = ("config.json",)
# The MLX model's weights: safetensors, or npz in the mlx-community repos.
MLX_WEIGHTS = ("weights.safetensors", "weights.npz")
MLX_PATTERNS = ["config.json", *MLX_WEIGHTS]
MLX_ORG = "mlx-community"
# faster-whisper model names whose mlx-community repo is not
# "whisper-<name>-mlx" (checked on the Hub, docs/decisions.md TASK-197).
MLX_REPOS = {
    "large-v3-turbo": "whisper-large-v3-turbo",
    "turbo": "whisper-large-v3-turbo",
}
MLX_SIZES = frozenset(
    {"tiny", "base", "small", "medium", "large", "large-v2", "large-v3"}
)
# A silence that Whisper fills with made-up words is dropped (mlx-whisper has
# no voice activity filter); needs word timestamps.
HALLUCINATION_SILENCE_S = 2.0
# Seconds given to each word of a collapsed run when there is no time left.
COLLAPSED_WORD_S = 0.02

logger = logging.getLogger(__name__)


def apple_silicon() -> bool:
    """Whether this machine is a Mac with an Apple Silicon chip."""
    return sys.platform == "darwin" and platform.machine() == "arm64"


def mlx_installed() -> bool:
    """Whether the mlx_whisper package can be found (it is not imported: that
    loads MLX and torch)."""
    return importlib.util.find_spec("mlx_whisper") is not None


def mlx_repo_id(name: str) -> str | None:
    """Return the Hugging Face repo of the MLX model for the whisper model
    called name, or None if there is none.

    name is a model size ("small", "medium.en", "large-v3-turbo") or a repo
    id with "/", which is returned as it is unless it is a faster-whisper
    (CTranslate2) repo.
    """
    if "/" in name:
        return None if "faster-whisper" in name else name
    if name in MLX_REPOS:
        return f"{MLX_ORG}/{MLX_REPOS[name]}"
    if name.removesuffix(".en") in MLX_SIZES:
        return f"{MLX_ORG}/whisper-{name}-mlx"
    return None


def mlx_model_dir(cfg: Settings) -> Path:
    """Return the directory that holds the MLX model of cfg.whisper_model."""
    return cfg.models_dir / MLX_DIRNAME / cfg.whisper_model.replace("/", "--")


def missing_mlx_files(model_dir: Path) -> list[str]:
    """Return the required MLX model files that model_dir lacks."""
    missing = [name for name in MLX_REQUIRED if not (model_dir / name).is_file()]
    if not any((model_dir / name).is_file() for name in MLX_WEIGHTS):
        missing.append(" or ".join(MLX_WEIGHTS))
    return missing


def download_mlx_model(cfg: Settings, *, force: bool = False) -> Path:
    """Download the MLX model of cfg.whisper_model and return its directory.

    Nothing is fetched if its files are there already, unless force. Raises
    ValueError if the model has no MLX version, huggingface_hub's errors if
    the download fails, and RuntimeError if the repo lacks a required file.
    """
    target = mlx_model_dir(cfg)
    if not force and not missing_mlx_files(target):
        logger.info("MLX whisper model %r is in %s", cfg.whisper_model, target)
        return target
    repo_id = mlx_repo_id(cfg.whisper_model)
    if repo_id is None:
        raise ValueError(f"whisper model {cfg.whisper_model!r} has no MLX version")
    use_project_hf_home(cfg)
    from huggingface_hub import snapshot_download

    logger.info("downloading MLX whisper model %s into %s", repo_id, target)
    snapshot_download(
        repo_id,
        local_dir=target,
        allow_patterns=MLX_PATTERNS,
        force_download=force,
    )
    missing = missing_mlx_files(target)
    if missing:
        raise RuntimeError(f"{repo_id} has no {', '.join(missing)}: not an MLX model")
    return target


def choose_backend(cfg: Settings) -> tuple[Backend, str | None]:
    """Return the backend that transcribes with cfg, and why it is not the
    one that was asked for (None if it is).

    faster_whisper is always faster-whisper. mlx and auto need an Apple
    Silicon Mac with mlx-whisper installed; auto also needs the MLX model to
    be downloaded and is silent on other machines, while mlx falls back to
    faster-whisper with a reason, except that a missing MLX model is an error
    when the transcription loads it (load_mlx_model).
    """
    if cfg.transcribe_backend == "faster_whisper":
        return "faster_whisper", None
    explicit = cfg.transcribe_backend == "mlx"
    if not apple_silicon():
        reason = "MLX needs an Apple Silicon Mac"
        return "faster_whisper", reason if explicit else None
    if not mlx_installed():
        return "faster_whisper", "mlx-whisper is not installed (uv sync)"
    if mlx_repo_id(cfg.whisper_model) is None:
        return "faster_whisper", f"{cfg.whisper_model!r} has no MLX version"
    if not explicit and missing_mlx_files(mlx_model_dir(cfg)):
        return "faster_whisper", (
            f"the MLX model of {cfg.whisper_model!r} is not downloaded; run "
            "`uv run python scripts/download_models.py`"
        )
    return "mlx", None


def active_backend(cfg: Settings) -> Backend:
    """Return choose_backend(cfg)'s backend, logging a warning if it is not
    the one that was asked for."""
    backend, reason = choose_backend(cfg)
    if reason is not None:
        logger.warning(
            "transcribe_backend %s: %s; using faster-whisper",
            cfg.transcribe_backend,
            reason,
        )
    return backend


class MlxWhisper:
    """The MLX Whisper model in model_dir, run by mlx_whisper.transcribe.

    mlx_whisper loads and caches the weights on its first call, and keeps
    them for the next ones.
    """

    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir

    def transcribe_chunk(
        self,
        wav: Path,
        language: str | None,
        hotwords: str | None,
        on_progress: Callable[[float], None],
    ) -> tuple[list[TimedWord], str]:
        """Transcribe the 16 kHz mono WAV in wav and return its words and
        language, with times relative to the chunk. language None lets
        Whisper detect it; hotwords, if set, prime the decoder as the
        initial prompt. on_progress gets 1.0 when the chunk is done: MLX
        reports nothing before.
        """
        import mlx_whisper

        result = mlx_whisper.transcribe(
            read_wav(wav),
            path_or_hf_repo=str(self.model_dir),
            language=language,
            word_timestamps=True,
            initial_prompt=hotwords,
            hallucination_silence_threshold=HALLUCINATION_SILENCE_S,
            verbose=None,
        )
        on_progress(1.0)
        return mlx_words(result), str(result.get("language") or language or "")


def load_mlx_model(cfg: Settings) -> MlxWhisper:
    """Return the MLX backend for cfg's model. Raises StepError if the model
    is not downloaded or mlx_whisper cannot be imported."""
    model_dir = mlx_model_dir(cfg)
    missing = missing_mlx_files(model_dir)
    if missing:
        raise StepError(
            f"MLX whisper model {cfg.whisper_model!r} is not downloaded: "
            f"{model_dir} lacks {', '.join(missing)}; run `uv run python "
            f"scripts/download_models.py --whisper-model {cfg.whisper_model}`"
        )
    try:
        import mlx_whisper  # noqa: F401
    except ImportError as exc:
        raise StepError(f"cannot load mlx-whisper: {exc}") from exc
    return MlxWhisper(model_dir)


def read_wav(path: Path) -> npt.NDArray[np.float32]:
    """Return the samples of a 16 kHz mono 16-bit PCM WAV as floats in -1..1
    (what mlx_whisper reads, without it running ffmpeg itself)."""
    with wave.open(str(path), "rb") as file:
        frames = file.readframes(file.getnframes())
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    return np.asarray(samples / 32768.0, dtype=np.float32)


def mlx_words(result: Mapping[str, Any]) -> list[TimedWord]:
    """Return the words of an mlx_whisper.transcribe result (made with
    word_timestamps=True) as TimedWords, the last of each segment marked.

    Whisper's alignment sometimes gives a run of words one time (no
    duration); the run is spread over the time up to the next word, or the
    end of its segment, so that no word is lost and the times keep rising.
    """
    words: list[TimedWord] = []
    floor = 0.0
    for segment in result.get("segments", []):
        heard = _spread_collapsed(segment.get("words", []), float(segment["end"]))
        for index, (word, raw_start, raw_end) in enumerate(heard):
            # A spread run can reach past the next word (no time to spread
            # into) and a segment can start before the last one's spread
            # words: never let a start go back in time.
            start = max(raw_start, floor)
            end = max(raw_end, start)
            floor = start
            words.append(
                TimedWord(
                    text=str(word["word"]),
                    start=start,
                    end=end,
                    prob=min(max(float(word.get("probability", 0.0)), 0.0), 1.0),
                    segment_end=index == len(heard) - 1,
                )
            )
    return words


def _spread_collapsed(
    words: list[Mapping[str, Any]], segment_end: float
) -> list[tuple[Mapping[str, Any], float, float]]:
    """Return (word, start, end) of each word, with every run of words that
    end when they start spread evenly up to the start of the word after the
    run (segment_end after the last word), or by COLLAPSED_WORD_S if there is
    no time."""
    timed: list[tuple[Mapping[str, Any], float, float]] = []
    index = 0
    while index < len(words):
        start = float(words[index]["start"])
        end = float(words[index]["end"])
        if end > start:
            timed.append((words[index], start, end))
            index += 1
            continue
        run = index
        while run < len(words) and float(words[run]["end"]) <= start:
            run += 1
        limit = float(words[run]["start"]) if run < len(words) else segment_end
        step = (limit - start) / (run - index)
        if step <= 0:
            step = COLLAPSED_WORD_S
        for offset, word in enumerate(words[index:run]):
            timed.append((word, start + offset * step, start + (offset + 1) * step))
        index = run
    return timed
