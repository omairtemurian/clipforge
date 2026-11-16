"""Tests of the YAMNet + RMS pass over a job's audio (pipeline/audio_analysis).

The WAV files are written with the standard library. The slow tests run the
YAMNet model that `make setup` downloads; see test_signals_laugh for the
pass over the sample video.
"""

import re
import wave
from pathlib import Path

import pytest
from clipforge.pipeline.audio_analysis import analyze_audio, open_wav
from clipforge.pipeline.loudness import FLOOR_DB
from clipforge.pipeline.step import StepError
from clipforge.pipeline.yamnet import Yamnet


def write_wav(
    path: Path, frames: int, *, channels: int = 1, width: int = 2, rate: int = 16000
) -> Path:
    """Write a WAV file of frames frames of digital silence."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(bytes(frames * channels * width))
    return path


@pytest.mark.parametrize(
    ("channels", "width", "rate", "found"),
    [
        (2, 2, 16000, "2 channel(s), 16-bit, 16000 Hz"),
        (1, 1, 16000, "1 channel(s), 8-bit, 16000 Hz"),
        (1, 2, 44100, "1 channel(s), 16-bit, 44100 Hz"),
    ],
)
def test_audio_that_is_not_16_khz_mono_16_bit_is_an_error(
    tmp_path: Path, channels: int, width: int, rate: int, found: str
) -> None:
    path = write_wav(
        tmp_path / "audio.wav", 100, channels=channels, width=width, rate=rate
    )
    with pytest.raises(StepError) as error:
        open_wav(path)
    assert str(error.value) == (
        f"{path} is not 16 kHz mono 16-bit PCM: {found}; run the ingest step again"
    )


@pytest.mark.parametrize("content", [b"not a wav file", None])
def test_audio_that_cannot_be_read_is_an_error(
    tmp_path: Path, content: bytes | None
) -> None:
    path = tmp_path / "audio.wav"
    if content is not None:
        path.write_bytes(content)
    with pytest.raises(StepError, match=f"^cannot read {re.escape(str(path))}: "):
        open_wav(path)


@pytest.mark.slow
def test_analysis_ends_where_the_audio_does(
    tmp_path: Path, yamnet_model: Yamnet
) -> None:
    path = write_wav(tmp_path / "audio.wav", 16000)
    progress: list[float] = []

    analysis = analyze_audio(
        path, 0.5, 10.0, yamnet_model, [13, 62], on_progress=progress.append
    )

    assert (analysis.start, analysis.end) == (0.5, 1.0)
    assert analysis.scores.shape == (1, 2)
    assert analysis.envelope.start == 0.5
    assert analysis.envelope.levels.tolist() == [FLOOR_DB] * 48
    assert progress == [1.0]


@pytest.mark.slow
def test_timeframe_after_the_audio_gives_an_empty_analysis(
    tmp_path: Path, yamnet_model: Yamnet
) -> None:
    path = write_wav(tmp_path / "audio.wav", 16000)
    progress: list[float] = []

    analysis = analyze_audio(
        path, 5.0, 10.0, yamnet_model, [13, 62], on_progress=progress.append
    )

    assert (analysis.start, analysis.end) == (1.0, 1.0)
    assert analysis.scores.shape == (0, 2)
    assert analysis.envelope.levels.shape == (0,)
    assert progress == []
