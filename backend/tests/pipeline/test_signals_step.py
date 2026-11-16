"""Tests of the signals step (SPEC 6.3): signals.json for a job's timeframe.

The slow tests run the YAMNet model that `make setup` downloads into
models/yamnet; they are skipped, saying so, when it is not there.

The silences of sample.mp4 are the gaps of at least 0.35 s between the
speech and laughs of expected.json. Its words fade in, so a silence can end
up to 0.06 s after the speech that follows it starts; and its laughs, which
are about 16 dB above the median level around them, are its energy peaks.
"""

import wave
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from clipforge.config import Settings
from clipforge.models import SignalEvent, SignalList
from clipforge.pipeline import ingest, signals
from clipforge.pipeline.signals import AUDIO_SHARE, detect_audio_signals
from clipforge.pipeline.step import (
    AUDIO,
    SIGNALS,
    SOURCE,
    StepError,
    StepSettings,
    load_json,
    load_step,
)

CopyJob = Callable[..., Path]
FRAME_S = 1 / 30
SILENCE_TOLERANCE_S = 0.1
RATE = 16000


def read_signals(job: Path) -> list[SignalEvent]:
    """Return the events in the signals.json of job."""
    return load_json(job / SIGNALS, SignalList, "signals").root


def gaps(expected: dict[str, Any], end: float) -> list[tuple[float, float]]:
    """Return the gaps of at least 0.35 s between the speech and laughs of
    expected and before and after them, up to end."""
    sounds = sorted(
        (sound["start"], sound["end"])
        for sound in expected["speech"] + expected["laughs"]
    )
    found, done = [], 0.0
    for start, stop in [*sounds, (end, end)]:
        if start - done >= 0.35:
            found.append((done, start))
        done = max(done, stop)
    return found


def write_audio(path: Path, samples: npt.NDArray[np.float64]) -> Path:
    """Write samples (-1..1) to path as 16 kHz mono 16-bit PCM."""
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(np.round(samples * 32767).astype("<i2").tobytes())
    return path


@pytest.fixture(scope="module")
def sample_run(copy_job: CopyJob, yamnet_cfg: Settings) -> tuple[Path, list[float]]:
    """A copy of the ingested sample on which the signals step has run, and
    the progress that the step reported."""
    job = copy_job()
    progress: list[float] = []
    settings = StepSettings(
        source="video.mp4", cfg=yamnet_cfg, on_progress=progress.append
    )
    assert signals.run(job, settings) == job / SIGNALS
    return job, progress


@pytest.mark.slow
def test_the_silences_of_the_sample_are_the_gaps_in_its_sound(
    sample_run: tuple[Path, list[float]], expected: dict[str, Any]
) -> None:
    events = read_signals(sample_run[0])
    assert events == sorted(events, key=lambda event: (event.start, event.kind))
    silences = [event for event in events if event.kind == "silence"]
    assert [(event.start, event.end) for event in silences] == [
        (
            pytest.approx(start, abs=SILENCE_TOLERANCE_S),
            pytest.approx(end, abs=SILENCE_TOLERANCE_S),
        )
        for start, end in gaps(expected, 60.0)
    ]
    assert all(event.intensity == 1.0 for event in silences)


@pytest.mark.slow
def test_the_energy_peaks_of_the_sample_are_its_laughs(
    sample_run: tuple[Path, list[float]], expected: dict[str, Any]
) -> None:
    events = read_signals(sample_run[0])
    peaks = [event for event in events if event.kind == "energy_peak"]
    laughs = expected["laughs"]
    for laugh in laughs:
        assert any(laugh["start"] < p.end and p.start < laugh["end"] for p in peaks)
    for peak in peaks:
        assert any(
            laugh["start"] - 0.1 <= peak.start < peak.end <= laugh["end"] + 0.1
            for laugh in laughs
        )
        # A laugh is so much louder than the speech around it that its
        # intensity is the most there is.
        assert peak.intensity == 1.0
    assert [event for event in events if event.kind == "scene_cut"] == []


@pytest.mark.slow
def test_progress_goes_from_the_audio_to_the_video(
    sample_run: tuple[Path, list[float]],
) -> None:
    # The audio is analyzed in one chunk; the video is read in two slices.
    assert sample_run[1] == pytest.approx([AUDIO_SHARE, (1 + AUDIO_SHARE) / 2, 1.0])


@pytest.mark.slow
def test_finished_work_is_skipped_unless_forced(
    copy_job: CopyJob, yamnet_cfg: Settings
) -> None:
    job = copy_job(20.0, 30.0)
    (job / SIGNALS).write_text("[]", encoding="utf-8")
    progress: list[float] = []
    settings = StepSettings(
        source="video.mp4", cfg=yamnet_cfg, on_progress=progress.append
    )

    assert signals.run(job, settings) == job / SIGNALS
    assert (job / SIGNALS).read_text(encoding="utf-8") == "[]"
    assert progress == [1.0]

    signals.run(job, settings, force=True)
    events = [event for event in read_signals(job) if event.kind == "silence"]
    assert len(events) == 3
    assert all(20.0 <= event.start < event.end <= 30.0 for event in events)


@pytest.mark.slow
def test_a_scene_cut_is_an_instant_in_signals_json(
    two_scenes: tuple[Path, float], yamnet_cfg: Settings, tmp_path: Path
) -> None:
    video, cut = two_scenes
    ingest.run(tmp_path, StepSettings(source=str(video)))
    signals.run(tmp_path, StepSettings(source=str(video), cfg=yamnet_cfg))

    cuts = [event for event in read_signals(tmp_path) if event.kind == "scene_cut"]
    assert [(event.start, event.end, event.intensity) for event in cuts] == [
        (pytest.approx(cut, abs=FRAME_S), pytest.approx(cut, abs=FRAME_S), 1.0)
    ]
    assert cuts[0].start == cuts[0].end


@pytest.mark.slow
def test_a_pause_between_two_tones_is_one_silence_in_source_time(
    yamnet_cfg: Settings, tmp_path: Path
) -> None:
    tone = 0.3 * np.sin(2 * np.pi * 440 * np.arange(3 * RATE // 2) / RATE)
    samples = np.concatenate([tone, np.zeros(RATE // 2), tone])
    audio = write_audio(tmp_path / AUDIO, samples)

    events = detect_audio_signals(audio, 0.5, 3.0, yamnet_cfg)

    assert [(event.kind, event.start, event.end) for event in events] == [
        ("silence", pytest.approx(1.5, abs=0.05), pytest.approx(2.0, abs=0.05))
    ]


def test_a_job_without_ingest_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(StepError, match="meta.json not found; run the ingest step"):
        signals.run(tmp_path, StepSettings(source="video.mp4"))
    assert not (tmp_path / SIGNALS).exists()


@pytest.mark.parametrize("name", [AUDIO, SOURCE])
def test_missing_audio_or_video_is_an_error(copy_job: CopyJob, name: str) -> None:
    job = copy_job()
    (job / name).unlink()
    with pytest.raises(StepError, match=f"{name} not found; run the ingest step"):
        signals.run(job, StepSettings(source="video.mp4"))


def test_a_missing_model_is_an_error_and_leaves_no_output(
    copy_job: CopyJob, tmp_path: Path
) -> None:
    job = copy_job()
    (job / SIGNALS).write_text("[]", encoding="utf-8")
    settings = StepSettings(
        source="video.mp4", cfg=Settings(models_dir=tmp_path / "models")
    )
    with pytest.raises(StepError, match="the YAMNet model is not downloaded"):
        signals.run(job, settings, force=True)
    assert not (job / SIGNALS).exists()


def test_signals_is_a_step() -> None:
    assert load_step("signals") is signals.run
