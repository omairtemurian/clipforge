"""Tests of the laugh and applause signals (SPEC 6.3) on the sample video.

The slow tests run the YAMNet model that `make setup` downloads into
models/yamnet; they are skipped, saying so, when it is not there.

The laughs of sample.mp4 are excerpts of a real CC0 recording of a crowd
laughing (assets/sfx). YAMNet hears Laughter in them (0.62-0.95 in the frames
inside them) and nowhere else (at most 0.001), so they are found within the
0.5 s of SPEC 9.3. Applause was checked by hand on real recordings
(docs/progress.md).
"""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from clipforge.config import Settings
from clipforge.models import SignalEvent
from clipforge.pipeline.audio_analysis import analyze_audio
from clipforge.pipeline.signal_merge import ScoredSpan
from clipforge.pipeline.signals import (
    ACTIVE_SCORE,
    detect_audio_signals,
    signal_event,
)
from clipforge.pipeline.step import AUDIO
from clipforge.pipeline.yamnet import Yamnet, frame_count

LAUGH_TOLERANCE_S = 0.5


@pytest.mark.slow
def test_laughs_are_detected_within_half_a_second_of_expected(
    ingested_sample: Path, yamnet_cfg: Settings, expected: dict[str, Any]
) -> None:
    events = detect_audio_signals(ingested_sample / AUDIO, 0.0, 60.0, yamnet_cfg)
    laughs = [(event.start, event.end) for event in events if event.kind == "laugh"]
    assert laughs == [
        (
            pytest.approx(laugh["start"], abs=LAUGH_TOLERANCE_S),
            pytest.approx(laugh["end"], abs=LAUGH_TOLERANCE_S),
        )
        for laugh in expected["laughs"]
    ]


@pytest.mark.slow
def test_yamnet_hears_laughter_in_the_laughs_and_nowhere_else(
    ingested_sample: Path, yamnet_model: Yamnet, expected: dict[str, Any]
) -> None:
    every_class = list(range(len(yamnet_model.class_names)))
    laughter = yamnet_model.class_index("Laughter")
    analysis = analyze_audio(
        ingested_sample / AUDIO, 0.0, 60.0, yamnet_model, every_class
    )
    starts = np.arange(len(analysis.scores)) * 0.48
    heard = np.zeros(len(starts), dtype=bool)
    for laugh in expected["laughs"]:
        inside = (starts >= laugh["start"]) & (starts + 0.96 <= laugh["end"])
        scores = analysis.scores[inside]
        assert len(scores) >= 2
        # Laughter is the top class of every frame inside a laugh.
        assert scores.argmax(axis=1).tolist() == [laughter] * len(scores)
        assert scores[:, laughter].min() > ACTIVE_SCORE
        heard |= (starts < laugh["end"]) & (starts + 0.96 > laugh["start"])
    assert analysis.scores[~heard, laughter].max() < 0.01


@pytest.mark.slow
def test_the_laughs_are_loud_enough_for_their_full_score(
    ingested_sample: Path, yamnet_model: Yamnet, expected: dict[str, Any]
) -> None:
    # They are 16 dB above the median level around them, so a laugh that
    # YAMNet scored 0.5 would have intensity 0.5.
    analysis = analyze_audio(ingested_sample / AUDIO, 0.0, 60.0, yamnet_model, [])
    for laugh in expected["laughs"]:
        span = ScoredSpan(laugh["start"], laugh["end"], 0.5)
        event = signal_event("laugh", span, analysis.envelope)
        assert event.intensity == 0.5


@pytest.mark.slow
def test_audio_read_in_chunks_is_analyzed_as_in_one_pass(
    ingested_sample: Path, yamnet_model: Yamnet
) -> None:
    columns = [yamnet_model.class_index(name) for name in ("Laughter", "Applause")]
    whole = analyze_audio(ingested_sample / AUDIO, 0.0, 60.0, yamnet_model, columns)
    progress: list[float] = []
    chunked = analyze_audio(
        ingested_sample / AUDIO,
        0.0,
        60.0,
        yamnet_model,
        columns,
        frames_per_chunk=7,
        on_progress=progress.append,
    )

    assert whole.scores.shape == chunked.scores.shape == (frame_count(960000), 2)
    np.testing.assert_allclose(chunked.scores, whole.scores, atol=1e-5)
    assert len(whole.envelope.levels) == 1 + (960000 - 400) // 160
    np.testing.assert_array_equal(chunked.envelope.levels, whole.envelope.levels)
    assert len(progress) == 18
    assert progress == sorted(progress) and progress[-1] == 1.0


@pytest.mark.slow
def test_only_the_timeframe_is_analyzed(
    ingested_sample: Path, yamnet_model: Yamnet
) -> None:
    laughter = yamnet_model.class_index("Laughter")
    analysis = analyze_audio(
        ingested_sample / AUDIO, 5.0, 50.0, yamnet_model, [laughter]
    )
    assert (analysis.start, analysis.end, analysis.envelope.start) == (5.0, 50.0, 5.0)
    assert analysis.scores.shape == (frame_count(45 * 16000), 1) == (93, 1)
    assert len(analysis.envelope.levels) == 1 + (45 * 16000 - 400) // 160


@pytest.mark.slow
def test_detection_keeps_to_the_timeframe_and_reports_progress(
    ingested_sample: Path, yamnet_cfg: Settings
) -> None:
    progress: list[float] = []

    events = detect_audio_signals(
        ingested_sample / AUDIO, 20.0, 40.0, yamnet_cfg, on_progress=progress.append
    )

    assert all(isinstance(event, SignalEvent) for event in events)
    assert all(20.0 <= event.start < event.end <= 40.0 for event in events)
    assert events == sorted(events, key=lambda event: (event.start, event.kind))
    assert progress == [1.0]
