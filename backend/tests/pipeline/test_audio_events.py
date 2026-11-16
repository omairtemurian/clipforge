"""Tests of the non-speech audio events (SPEC-v2 3.2): per-second scores of
laughter, applause, cheering and music, and how they reach candidate scoring.

The model is faked with synthetic scores (the real one is downloaded by
scripts/download_models.py); the slow test runs the installed model and is
skipped when it is not there.
"""

import wave
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pytest
from builders import event
from clipforge.config import Settings
from clipforge.model_files import YAMNET_CLASS_MAP, yamnet_model_dir
from clipforge.models import (
    AudioEventList,
    AudioEventTrack,
    CandidateList,
    SignalList,
)
from clipforge.pipeline import signals, yamnet
from clipforge.pipeline.audio_events import EVENT_CLASSES, audio_track
from clipforge.pipeline.score import component_weights, energy_score, score_candidate
from clipforge.pipeline.signal_merge import ScoredSpan, per_second_scores
from clipforge.pipeline.step import (
    AUDIO,
    AUDIO_EVENTS,
    SIGNALS,
    StepError,
    StepSettings,
    load_json,
)
from clipforge.pipeline.yamnet import Yamnet, read_class_map
from fakes import LLM_RESPONSE

RATE = 16000
CLASS_NAMES = ("Speech", "Laughter", "Applause", "Cheering", "Music")
FakeScores = dict[str, dict[int, float]]
SPEC_WEIGHTS = {"llm": 0.6, "laugh": 0.25, "energy": 0.15}
# A 10-30 s candidate with the LLM scores of the SPEC example.
CANDIDATE = (
    CandidateList.model_validate_json(LLM_RESPONSE.read_bytes())
    .clips[0]
    .model_copy(update={"start": 10.0, "end": 30.0})
)


class FakeSession:
    """An onnxruntime session that scores YAMNet frames from a table.

    scores[class name][frame index] is the score; the other frames score 0.
    """

    def __init__(self, scores: FakeScores) -> None:
        self.scores = scores

    def run(
        self, outputs: list[str], inputs: dict[str, npt.NDArray[np.float32]]
    ) -> list[npt.NDArray[np.float32]]:
        frames = yamnet.frame_count(len(inputs[yamnet.INPUT]))
        table = np.zeros((frames, len(CLASS_NAMES)), dtype=np.float32)
        for name, by_frame in self.scores.items():
            for frame, score in by_frame.items():
                if frame < frames:
                    table[frame, CLASS_NAMES.index(name)] = score
        return [table]


def fake_model(scores: FakeScores) -> Yamnet:
    return Yamnet(FakeSession(scores), CLASS_NAMES)


def write_tone(path: Path, seconds: float) -> Path:
    """Write a steady 440 Hz tone to path as 16 kHz mono 16-bit PCM."""
    times = np.arange(round(seconds * RATE)) / RATE
    samples = np.round(0.3 * np.sin(2 * np.pi * 440 * times) * 32767)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(samples.astype("<i2").tobytes())
    return path


def test_each_second_has_the_highest_score_of_the_frames_that_overlap_it() -> None:
    frames = [
        ScoredSpan(0.24, 0.72, 0.2),
        ScoredSpan(0.72, 1.2, 0.6),  # across the first second's end
        ScoredSpan(1.2, 1.68, 0.4),
        ScoredSpan(3.0, 3.48, 0.9),  # starts exactly at a second
    ]
    assert per_second_scores(frames, 0.0, 4.0) == [0.6, 0.6, 0.0, 0.9]


def test_seconds_count_from_the_start_and_the_last_one_is_cut_at_the_end() -> None:
    frames = [ScoredSpan(10.5, 10.98, 0.5), ScoredSpan(12.0, 12.48, 0.8)]
    assert per_second_scores(frames, 10.0, 12.3) == [0.5, 0.0, 0.8]
    assert per_second_scores(frames, 10.0, 10.0) == []
    assert per_second_scores([], 0.0, 2.0) == [0.0, 0.0]


def test_a_track_is_rounded_and_starts_at_the_timeframe() -> None:
    track = audio_track("cheer", [ScoredSpan(5.3, 5.78, 0.123456)], 5.0, 7.0)
    assert track == AudioEventTrack(kind="cheer", start=5.0, scores=[0.123, 0.0])


def test_the_events_are_the_four_audience_and_music_classes() -> None:
    assert EVENT_CLASSES == {
        "laugh": "Laughter",
        "applause": "Applause",
        "cheer": "Cheering",
        "music": "Music",
    }


def test_a_class_map_without_an_event_class_is_an_error() -> None:
    model = Yamnet(None, ("Speech", "Laughter"))
    with pytest.raises(StepError, match="has no class 'Applause'"):
        model.class_index(EVENT_CLASSES["applause"])


def test_the_class_names_are_in_the_installed_class_map(yamnet_cfg: Settings) -> None:
    names = read_class_map(yamnet_model_dir(yamnet_cfg) / YAMNET_CLASS_MAP)
    assert all(name in names for name in EVENT_CLASSES.values())


def test_the_analysis_has_events_and_per_second_scores_for_every_class(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Frame i stands for [0.48 i + 0.24, 0.48 i + 0.72]: frames 2-5 are 1.2-3.12 s.
    scores: FakeScores = {
        "Cheering": {i: 0.9 for i in range(2, 6)},
        "Music": {i: 0.5 for i in range(8, 12)},
    }
    monkeypatch.setattr(signals.yamnet, "load_yamnet", lambda cfg: fake_model(scores))
    audio = write_tone(tmp_path / AUDIO, 6.0)

    found = signals.analyze_signals(audio, 0.0, 6.0, Settings())

    by_kind = {t.kind: t for t in found.tracks}
    assert list(by_kind) == ["laugh", "applause", "cheer", "music"]
    assert by_kind["cheer"].scores == [0.0, 0.9, 0.9, 0.9, 0.0, 0.0]
    assert by_kind["music"].scores == [0.0, 0.0, 0.0, 0.0, 0.5, 0.5]
    assert by_kind["laugh"].scores == [0.0] * 6
    spans = {
        e.kind: (e.start, e.end) for e in found.events if e.kind in {"cheer", "music"}
    }
    assert spans == {"cheer": (1.2, 3.12), "music": (4.08, 6.0)}


def test_the_step_writes_the_scores_next_to_the_signals(
    monkeypatch: pytest.MonkeyPatch, copy_job: Any
) -> None:
    scores: FakeScores = {"Applause": {i: 0.8 for i in range(4, 10)}}
    monkeypatch.setattr(signals.yamnet, "load_yamnet", lambda cfg: fake_model(scores))
    job = copy_job()
    signals.run(job, StepSettings(source="video.mp4", cfg=Settings()))

    tracks = load_json(job / AUDIO_EVENTS, AudioEventList, "audio events").root
    assert [t.kind for t in tracks] == list(EVENT_CLASSES)
    assert all(len(t.scores) == 60 for t in tracks)
    assert tracks[1].scores[:7] == [0.0, 0.0, 0.8, 0.8, 0.8, 0.8, 0.0]
    assert (job / SIGNALS).is_file()
    applause = load_json(job / SIGNALS, SignalList, "signals").root
    assert any(e.kind == "applause" for e in applause)


@pytest.mark.parametrize("kind", ["applause", "cheer", "energy_peak"])
def test_crowd_events_and_energy_peaks_fill_the_clips_energy(kind: Any) -> None:
    assert energy_score(10.0, 30.0, [event(kind, 12.0, 17.0)]) == 0.25


def test_music_and_laughs_do_not_fill_the_clips_energy() -> None:
    events = [event("music", 10.0, 30.0), event("laugh", 10.0, 30.0)]
    assert energy_score(10.0, 30.0, events) == 0.0


def test_overlapping_crowd_events_and_peaks_count_once() -> None:
    events = [
        event("cheer", 12.0, 16.0),
        event("applause", 14.0, 18.0),
        event("energy_peak", 13.0, 15.0),
    ]
    assert energy_score(10.0, 30.0, events) == 0.3


def test_a_cheered_clip_scores_higher_than_the_same_clip_without_the_cheer() -> None:
    weights = component_weights("podcast", SPEC_WEIGHTS)
    quiet = score_candidate(CANDIDATE, [event("music", 10.0, 30.0)], weights)
    cheered = score_candidate(CANDIDATE, [event("cheer", 10.0, 30.0)], weights)

    assert quiet.scores.energy == 0.0
    assert cheered.scores.energy == 1.0
    assert cheered.scores.overall > quiet.scores.overall


@pytest.mark.slow
def test_the_installed_model_scores_laughter_where_the_sample_laughs(
    copy_job: Any, yamnet_cfg: Settings, expected: dict[str, Any]
) -> None:
    job = copy_job()
    signals.run(job, StepSettings(source="video.mp4", cfg=yamnet_cfg))

    tracks = load_json(job / AUDIO_EVENTS, AudioEventList, "audio events").root
    laugh = next(t for t in tracks if t.kind == "laugh")
    assert [t.kind for t in tracks] == list(EVENT_CLASSES)
    assert all(len(t.scores) == 60 for t in tracks)
    for sound in expected["laughs"]:
        middle = int((sound["start"] + sound["end"]) / 2)
        assert laugh.scores[middle] > 0.3
