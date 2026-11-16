"""Tests of the Pro Edit signals adapter (SPEC-v3 3.2, TASK-205).

The job is the committed fixture sample.mp4 (its transcript.json, a copy of
the video) with a signals.json of the events the signals step finds in it
(FIXTURE_LAUGHS, the silences between the speech and laughs of expected.json,
a scene cut and a loudness peak at the first laugh). The face detector is a
stand-in that finds one face in every frame; the motion is measured on the
real video. The signals of clip 7 (16.5-34.5 s) are compared with
fixtures/proedit_signals_expected.json; the motion energies, which depend on
the ffmpeg decoder, within MOTION_TOLERANCE.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from builders import FIXTURE_LAUGHS, cut, event, make_clip, source_meta
from clipforge.config import Settings
from clipforge.models import (
    CaptionMark,
    CaptionStyle,
    Clip,
    FaceBox,
    MotionTrack,
    SignalList,
)
from clipforge.pipeline.face_cache import FACE_CACHE
from clipforge.pipeline.faces import Frame
from clipforge.pipeline.step import (
    META,
    MOTION,
    SIGNALS,
    SOURCE,
    TRANSCRIPT,
    StepError,
    write_json,
)
from clipforge.proedit.signals import build_signals, plan_timing
from fakes import FIXTURES

EXPECTED = FIXTURES / "proedit_signals_expected.json"
MOTION_TOLERANCE = 0.002
FACE = FaceBox(x=300.0, y=90.0, width=100.0, height=120.0, score=0.9, mouth=0.1)
# The silences between the speech and laughs of expected.json inside the clip.
SILENCES = (event("silence", 32.85, 33.15), event("silence", 20.0, 20.25))


class CountingDetector:
    """A face detector that finds FACE (in 640x360 analysis pixels) in every
    frame and counts the frames it searched."""

    def __init__(self) -> None:
        self.frames = 0

    def __call__(self, frame: Frame) -> list[FaceBox]:
        self.frames += 1
        return [FACE]


@pytest.fixture
def job(tmp_path: Path, sample_mp4: Path) -> Path:
    """A job directory of the fixture: source, meta, transcript, signals."""
    shutil.copy(sample_mp4, tmp_path / SOURCE)
    shutil.copy(FIXTURES / "transcript.json", tmp_path / TRANSCRIPT)
    write_json(tmp_path / META, source_meta())
    events = [
        *FIXTURE_LAUGHS,
        event("energy_peak", 33.4, 34.0, 0.9),
        event("applause", 27.2, 27.6, 0.5),
        event("music", 17.0, 18.0, 0.5),
        *SILENCES,
        cut(22.0),
        cut(40.0),
    ]
    write_json(tmp_path / SIGNALS, SignalList(events))
    return tmp_path


def fixture_clip(**changes: Any) -> Clip:
    """Clip 7 over 16.5-34.5 s of the fixture."""
    return make_clip("clean", start=16.5, end=34.5, **changes)


def dump(job: Path, clip: Clip) -> dict[str, Any]:
    """Return the signals of clip as the JSON they are stored in."""
    detector = CountingDetector()
    signals = build_signals(job, clip, cfg=Settings(), detect=detector)
    dumped: dict[str, Any] = json.loads(signals.model_dump_json())
    return dumped


def test_the_signals_of_the_fixture_match_the_recorded_json(job: Path) -> None:
    got = dump(job, fixture_clip())
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))

    energies = [(m["start"], m["end"], m["energy"]) for m in got.pop("motion")]
    recorded = [(m["start"], m["end"], m["energy"]) for m in expected.pop("motion")]
    got_spans, expected_spans = got.pop("motion_spans"), expected.pop("motion_spans")

    assert got == expected
    assert [e[:2] for e in energies] == [e[:2] for e in recorded]
    assert [e[2] for e in energies] == pytest.approx(
        [e[2] for e in recorded], abs=MOTION_TOLERANCE
    )
    assert [(s["start"], s["end"]) for s in got_spans] == [
        (s["start"], s["end"]) for s in expected_spans
    ]


def test_key_numbers_of_the_fixture_signals(job: Path) -> None:
    got = dump(job, fixture_clip())

    assert got["duration"] == 18.0
    assert (got["fps"], got["width"], got["height"]) == (30, 1280, 720)
    assert got["words"][0]["text"] == "Then"
    assert got["words"][0]["start"] == pytest.approx(0.4, abs=0.001)
    assert got["scene_cuts"] == [5.5]
    assert [(p["text"], p["kind"]) for p in got["punchlines"]] == [
        ("night.", "applause"),
        ("cheese.", "laugh"),
    ]
    assert {e["kind"] for e in got["events"]} == {"laugh", "applause", "energy_peak"}
    assert len(got["sentences"]) == 4
    assert [t["speaker"] for t in got["speaker_turns"]] == ["S0"]
    assert len(got["motion"]) == 18


def test_energy_peaks_and_reactions_are_in_clip_time(job: Path) -> None:
    got = dump(job, fixture_clip())

    laugh = next(e for e in got["events"] if e["kind"] == "laugh")
    applause = next(e for e in got["events"] if e["kind"] == "applause")

    assert (laugh["start"], laugh["end"]) == (16.86, 18.0)
    assert (applause["start"], applause["end"]) == (10.7, 11.1)
    # The laugh of 14.16-16.08 ends before the clip starts.
    assert [e["kind"] for e in got["events"]] == ["applause", "laugh", "energy_peak"]
    assert [e["start"] for e in got["events"]] == [10.7, 16.86, 16.9]


def test_a_scene_cut_starts_a_new_face_track_at_normalized_boxes(job: Path) -> None:
    got = dump(job, fixture_clip())

    first, second = got["faces"]

    assert [(t["track"], t["start"], t["end"]) for t in (first, second)] == [
        (0, 0.0, 5.4),
        (1, 5.5, 17.9),
    ]
    assert (first["subject_share"], second["subject_share"]) == (1.0, 1.0)
    assert (len(first["samples"]), len(second["samples"])) == (11, 25)
    assert first["samples"][1] == {
        "t": 0.5,
        "x": 0.4688,
        "y": 0.25,
        "width": 0.1562,
        "height": 0.3333,
    }


def test_cut_ranges_move_every_signal_to_the_rendered_time(job: Path) -> None:
    whole = dump(job, fixture_clip())
    cutting = dump(job, fixture_clip(cut_ranges=[(20.0, 20.25)]))

    assert cutting["duration"] == pytest.approx(17.75, abs=0.04)
    before = next(e for e in whole["events"] if e["kind"] == "laugh")
    after = next(e for e in cutting["events"] if e["kind"] == "laugh")
    assert after["start"] == pytest.approx(before["start"] - 0.25, abs=0.04)
    # The silence at 20.0-20.25 s is cut away whole; the second it falls in
    # is split in two.
    assert len(cutting["silences"]) == len(whole["silences"]) - 1
    assert len(cutting["motion"]) == len(whole["motion"]) + 1


def test_emphasis_words_and_marks_set_the_words_emphasis(job: Path) -> None:
    marks = [
        CaptionMark(start=19.24, emphasis=False),
        CaptionMark(start=32.43, emoji="🔥"),
    ]
    clip = fixture_clip(
        emphasis_words=["fridges", "hawk"],
        caption_style=CaptionStyle(word_marks=marks),
    )

    words = {w["text"]: w for w in dump(job, clip)["words"]}

    assert words["hawk."]["emphasis"] is True
    # A mark that pins emphasis off beats the clip's emphasis words.
    assert words["fridges."]["emphasis"] is False
    assert words["cheese."]["emoji"] == "🔥"
    assert words["the"]["emoji"] is None


def test_stored_motion_is_reused_when_it_covers_the_clip(job: Path) -> None:
    stored = [round(0.01 * (i % 7), 2) for i in range(60)]
    write_json(job / MOTION, MotionTrack(start=0.0, scores=stored))

    got = dump(job, fixture_clip())

    # The seconds 16 and 34 are only partly in the clip.
    assert [m["energy"] for m in got["motion"]] == stored[16:35]
    assert (got["motion"][0]["start"], got["motion"][0]["end"]) == (0.0, 0.5)
    assert got["motion"][-1]["end"] == 18.0


def test_the_second_build_reuses_the_face_cache(job: Path) -> None:
    detector = CountingDetector()
    first = build_signals(job, fixture_clip(), cfg=Settings(), detect=detector)
    searched = detector.frames

    second = build_signals(job, fixture_clip(), cfg=Settings(), detect=detector)

    assert searched == 180
    assert detector.frames == searched
    assert (job / FACE_CACHE).is_file()
    assert first.faces == second.faces


def test_a_clip_without_a_transcript_is_a_step_error(job: Path) -> None:
    (job / TRANSCRIPT).unlink()

    with pytest.raises(StepError, match="transcribe"):
        build_signals(job, fixture_clip(), cfg=Settings(), detect=CountingDetector())


def test_plan_timing_carries_word_starts_and_punchline_spans(job: Path) -> None:
    signals = build_signals(
        job, fixture_clip(), cfg=Settings(), detect=CountingDetector()
    )

    timing = plan_timing(signals, beats=[1.0, 2.0])

    assert timing.fps == 30
    assert timing.duration == 18.0
    assert timing.word_starts[0] == signals.words[0].start
    assert timing.beats == (1.0, 2.0)
    assert timing.punchlines == ((10.23, 10.6), (15.93, 16.35))
