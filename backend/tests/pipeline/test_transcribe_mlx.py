"""Tests of the MLX Whisper backend (TASK-197): choosing it, normalising its
output, and loading its model, without downloading or running a model. The
engine test at the end runs the real model, when mlx-whisper and the model
are there."""

import json
import logging
import sys
import types
import wave
from pathlib import Path
from typing import Any

import pytest
from clipforge.config import Settings
from clipforge.pipeline import transcribe, transcribe_mlx
from clipforge.pipeline.step import StepError
from clipforge.pipeline.transcribe_mlx import (
    MlxWhisper,
    choose_backend,
    download_mlx_model,
    load_mlx_model,
    missing_mlx_files,
    mlx_model_dir,
    mlx_repo_id,
    mlx_words,
    read_wav,
)
from clipforge.pipeline.transcript_merge import Chunk, build_transcript, merge_chunks

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MODELS_DIR = Path(__file__).resolve().parents[3] / "models"
MLX_RESULT: dict[str, Any] = json.loads((FIXTURES / "mlx_result.json").read_text())


def machine(
    monkeypatch: pytest.MonkeyPatch, *, apple: bool = True, installed: bool = True
) -> None:
    """Pretend this is (or is not) an Apple Silicon Mac with mlx-whisper."""
    monkeypatch.setattr(transcribe_mlx, "apple_silicon", lambda: apple)
    monkeypatch.setattr(transcribe_mlx, "mlx_installed", lambda: installed)


def with_model(cfg: Settings) -> Settings:
    """Put the files of cfg's MLX model in place (empty: nothing loads them)."""
    model_dir = mlx_model_dir(cfg)
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}")
    (model_dir / "weights.npz").write_bytes(b"")
    return cfg


@pytest.mark.parametrize(
    ("name", "repo"),
    [
        ("small", "mlx-community/whisper-small-mlx"),
        ("large-v3", "mlx-community/whisper-large-v3-mlx"),
        ("base.en", "mlx-community/whisper-base.en-mlx"),
        ("large-v3-turbo", "mlx-community/whisper-large-v3-turbo"),
        ("me/whisper-mlx-x", "me/whisper-mlx-x"),
        ("Systran/faster-whisper-small", None),
        ("distil-small.en", None),
    ],
)
def test_the_mlx_repo_of_a_whisper_model(name: str, repo: str | None) -> None:
    assert mlx_repo_id(name) == repo


def test_faster_whisper_is_chosen_when_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch)
    cfg = with_model(Settings(models_dir=tmp_path, transcribe_backend="faster_whisper"))

    assert choose_backend(cfg) == ("faster_whisper", None)


def test_auto_is_mlx_on_apple_silicon_with_the_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch)
    cfg = with_model(Settings(models_dir=tmp_path, transcribe_backend="auto"))

    assert choose_backend(cfg) == ("mlx", None)


def test_auto_on_another_machine_is_silently_faster_whisper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch, apple=False)
    cfg = Settings(models_dir=tmp_path, transcribe_backend="auto")

    assert choose_backend(cfg) == ("faster_whisper", None)


@pytest.mark.parametrize(
    ("apple", "installed", "message"),
    [
        (False, True, "needs an Apple Silicon Mac"),
        (True, False, "mlx-whisper is not installed"),
    ],
)
def test_mlx_that_cannot_run_falls_back_to_faster_whisper_with_a_warning(
    apple: bool,
    installed: bool,
    message: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    machine(monkeypatch, apple=apple, installed=installed)
    cfg = with_model(Settings(models_dir=tmp_path, transcribe_backend="mlx"))

    with caplog.at_level(logging.WARNING, logger=transcribe_mlx.logger.name):
        backend = transcribe_mlx.active_backend(cfg)

    assert backend == "faster_whisper"
    [record] = caplog.records
    assert message in record.getMessage()
    assert "using faster-whisper" in record.getMessage()


def test_auto_without_the_package_on_a_mac_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    machine(monkeypatch, installed=False)
    cfg = Settings(models_dir=tmp_path, transcribe_backend="auto")

    with caplog.at_level(logging.WARNING, logger=transcribe_mlx.logger.name):
        assert transcribe_mlx.active_backend(cfg) == "faster_whisper"

    assert "mlx-whisper is not installed" in caplog.text


def test_auto_without_the_model_falls_back_but_mlx_asks_for_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch)

    backend, reason = choose_backend(Settings(models_dir=tmp_path))
    assert backend == "faster_whisper"
    assert reason is not None and "not downloaded" in reason

    explicit = Settings(models_dir=tmp_path, transcribe_backend="mlx")
    assert choose_backend(explicit) == ("mlx", None)
    with pytest.raises(StepError, match="MLX whisper model 'small' is not downloaded"):
        load_mlx_model(explicit)


def test_a_model_without_an_mlx_version_uses_faster_whisper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch)
    cfg = Settings(models_dir=tmp_path, whisper_model="Systran/faster-whisper-small")

    backend, reason = choose_backend(cfg)

    assert backend == "faster_whisper"
    assert reason is not None and "has no MLX version" in reason


def test_load_model_loads_the_backend_that_was_chosen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine(monkeypatch)
    cfg = with_model(Settings(models_dir=tmp_path))

    model = transcribe.load_model(cfg)

    assert isinstance(model, MlxWhisper)
    assert model.model_dir == mlx_model_dir(cfg)


def test_mlx_words_are_the_fixture_result_as_timed_words() -> None:
    words = mlx_words(MLX_RESULT)

    raw = [w for s in MLX_RESULT["segments"] for w in s["words"]]
    assert [w.text for w in words] == [w["word"] for w in raw]
    assert [(w.start, w.end, w.prob) for w in words[:2]] == [
        (raw[0]["start"], raw[0]["end"], raw[0]["probability"]),
        (raw[1]["start"], raw[1]["end"], raw[1]["probability"]),
    ]
    assert all(0.0 <= w.prob <= 1.0 and w.end > w.start for w in words)
    assert all(a.start <= b.start for a, b in zip(words, words[1:], strict=False))
    ends = [i for i, w in enumerate(words) if w.segment_end]
    assert len(ends) == len(MLX_RESULT["segments"])
    assert words[-1].segment_end


def test_mlx_word_starts_never_go_back_in_time() -> None:
    # A collapsed run with no room before the next word (spread by
    # COLLAPSED_WORD_S past it) and a segment starting before the previous
    # segment's last word: starts must still rise and every word keep a time.
    result = {
        "segments": [
            {
                "end": 1.0,
                "words": [
                    {"word": " a", "start": 1.0, "end": 1.0, "probability": 0.9},
                    {"word": " b", "start": 1.0, "end": 1.0, "probability": 0.9},
                    {"word": " c", "start": 0.99, "end": 1.2, "probability": 0.9},
                ],
            },
            {
                "end": 2.0,
                "words": [
                    {"word": " d", "start": 0.98, "end": 1.5, "probability": 0.9}
                ],
            },
        ]
    }

    words = mlx_words(result)

    assert [w.text for w in words] == [" a", " b", " c", " d"]
    assert [round(w.start, 3) for w in words] == [1.0, 1.02, 1.02, 1.02]
    assert all(w.end >= w.start for w in words)
    assert all(a.start <= b.start for a, b in zip(words, words[1:], strict=False))


def test_the_fixture_result_becomes_a_transcript() -> None:
    words = mlx_words(MLX_RESULT)

    transcript = build_transcript(
        merge_chunks([(Chunk(20.0, 42.0), words)]), language="en", duration=60.0
    )

    assert transcript.language == "en"
    spoken = [w for s in transcript.segments for w in s.words]
    assert len(spoken) == len(words)
    assert spoken[0].start == pytest.approx(20.0 + words[0].start, abs=1e-3)
    assert all(0.0 <= w.prob <= 1.0 for w in spoken)


def test_words_that_collapse_to_one_time_are_spread_not_lost() -> None:
    def word(text: str, start: float, end: float) -> dict[str, Any]:
        return {"word": text, "start": start, "end": end, "probability": 0.9}

    result = {
        "segments": [
            {
                "end": 5.0,
                "words": [
                    word(" a", 1.0, 1.5),
                    word(" b", 2.0, 2.0),
                    word(" c", 2.0, 2.0),
                    word(" d", 3.0, 3.5),
                    word(" e", 4.0, 4.0),
                ],
            },
            {"end": 7.0, "words": [word(" f", 6.0, 6.0)]},
        ]
    }

    words = mlx_words(result)

    assert [w.text for w in words] == [" a", " b", " c", " d", " e", " f"]
    assert [(w.start, w.end) for w in words] == [
        (1.0, 1.5),
        (2.0, 2.5),
        (2.5, 3.0),
        (3.0, 3.5),
        (4.0, 5.0),
        (6.0, 7.0),
    ]
    assert [w.segment_end for w in words] == [False] * 4 + [True, True]


def test_a_collapsed_word_with_no_time_left_still_gets_a_duration() -> None:
    result = {
        "segments": [
            {
                "end": 2.0,
                "words": [{"word": " x", "start": 2.0, "end": 2.0, "probability": 0.5}],
            }
        ]
    }

    [word] = mlx_words(result)

    assert word.end - word.start == pytest.approx(transcribe_mlx.COLLAPSED_WORD_S)


def test_a_wav_is_read_as_floats(tmp_path: Path) -> None:
    path = tmp_path / "a.wav"
    with wave.open(str(path), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(16000)
        file.writeframes((16384).to_bytes(2, "little", signed=True) * 3)

    samples = read_wav(path)

    assert samples.dtype.name == "float32"
    assert samples.tolist() == [0.5, 0.5, 0.5]


def test_a_chunk_is_transcribed_with_the_mlx_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_transcribe(audio: object, **kwargs: Any) -> dict[str, Any]:
        calls.append({"audio": audio, **kwargs})
        return MLX_RESULT

    package = types.ModuleType("mlx_whisper")
    package.transcribe = fake_transcribe  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_whisper", package)
    wav = tmp_path / "a.wav"
    with wave.open(str(wav), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(16000)
        file.writeframes(b"\0\0" * 16)
    progress: list[float] = []
    model = MlxWhisper(tmp_path / "model")

    words, language = transcribe._transcribe_chunk(
        model, wav, "en", "Kubernetes", progress.append
    )

    [call] = calls
    assert call["path_or_hf_repo"] == str(tmp_path / "model")
    assert call["language"] == "en" and call["word_timestamps"] is True
    assert call["initial_prompt"] == "Kubernetes"
    assert len(call["audio"]) == 16
    assert language == "en" and len(words) == len(mlx_words(MLX_RESULT))
    assert progress == [1.0]


def test_the_language_is_detected_by_mlx_when_not_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = types.ModuleType("mlx_whisper")
    package.transcribe = lambda audio, **kw: {"language": "de", "segments": []}  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_whisper", package)
    wav = tmp_path / "a.wav"
    with wave.open(str(wav), "wb") as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(16000)
        file.writeframes(b"\0\0")

    words, language = MlxWhisper(tmp_path).transcribe_chunk(
        wav, None, None, lambda done: None
    )

    assert words == [] and language == "de"


def test_the_model_is_downloaded_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repos: list[str] = []

    def fake_download(repo_id: str, *, local_dir: Path, **kwargs: Any) -> None:
        repos.append(repo_id)
        local_dir.mkdir(parents=True, exist_ok=True)
        (local_dir / "config.json").write_text("{}")
        (local_dir / "weights.safetensors").write_bytes(b"")

    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_download)
    monkeypatch.delenv("HF_HOME", raising=False)
    cfg = Settings(models_dir=tmp_path)

    path = download_mlx_model(cfg)
    download_mlx_model(cfg)

    assert path == tmp_path / "whisper-mlx" / "small"
    assert repos == ["mlx-community/whisper-small-mlx"]
    assert missing_mlx_files(path) == []


def test_a_model_without_an_mlx_version_cannot_be_downloaded(
    tmp_path: Path,
) -> None:
    cfg = Settings(models_dir=tmp_path, whisper_model="distil-small.en")

    with pytest.raises(ValueError, match="has no MLX version"):
        download_mlx_model(cfg)


@pytest.mark.engine_mlx_whisper
def test_the_real_mlx_model_transcribes_the_fixture_and_the_overlap_merges(
    tmp_path: Path,
) -> None:
    cfg = Settings(models_dir=MODELS_DIR, transcribe_backend="mlx")
    if not (transcribe_mlx.apple_silicon() and transcribe_mlx.mlx_installed()):
        pytest.skip("mlx-whisper needs an Apple Silicon Mac with the package")
    if missing_mlx_files(mlx_model_dir(cfg)):
        pytest.skip("the MLX model is not downloaded; run `make setup`")
    from clipforge.ffmpeg import extract_audio_wav

    audio = extract_audio_wav(FIXTURES / "sample.mp4", tmp_path / "a.wav")
    model = transcribe.load_model(cfg)
    assert isinstance(model, MlxWhisper)
    first = Chunk(0.0, 40.0)
    second = Chunk(30.0, 60.0)
    heard = []
    for chunk in (first, second):
        wav = extract_audio_wav(
            audio,
            tmp_path / "c.wav",
            start=chunk.start,
            duration=chunk.end - chunk.start,
        )
        words, _ = transcribe._transcribe_chunk(model, wav, "en", None, lambda d: None)
        assert all(a.start <= b.start for a, b in zip(words, words[1:], strict=False))
        heard.append((chunk, words))

    merged = merge_chunks(heard)

    assert all(a.start <= b.start for a, b in zip(merged, merged[1:], strict=False))
    assert len(merged) <= sum(len(words) for _, words in heard)
