"""Clip anything (SPEC-v2 3.2): motion energy, frame captions, audio events
and scene cuts go into the curate prompt, so a video without speech still
yields clips.

The motion is measured with the real ffmpeg on the fixture video and on a
silent test video (a still grey picture, then a moving test pattern). Only
the external boundaries are faked: the Ollama vision model (respx, see
vlm_fakes) and the LLM (FakeLLMClient).
"""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx
from clipforge import engines
from clipforge.config import Settings
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import (
    CandidateList,
    ClipCandidate,
    FrameCaption,
    FrameCaptionList,
    MotionTrack,
    ProcessingSettings,
    ScoredList,
    SignalEvent,
    SignalList,
    Transcript,
)
from clipforge.pipeline import curate, enrich, ingest, score, snap, visuals
from clipforge.pipeline.auto_cut import new_clip_cuts
from clipforge.pipeline.curate_prompt import system_prompt, timeline_lines
from clipforge.pipeline.motion import (
    MOTION_FLOOR,
    MotionSpan,
    measure_motion,
    motion_spans,
)
from clipforge.pipeline.step import (
    CANDIDATES,
    FRAME_CAPTIONS,
    MOTION,
    SIGNALS,
    SNAPPED,
    TRANSCRIPT,
    StepSettings,
    load_meta,
    write_json,
)
from fakes import FakeLLMClient
from vlm_fakes import mock_ollama, use_server

STILL_S = MOVING_S = 10.0
CFG = Settings(clip_min_s=5, clip_max_s=60, max_clips_from_llm=30)
ANYTHING = ProcessingSettings(clip_anything=True)
CAPTIONS = ("A plain grey screen.", "Colourful shapes\n move  across it.")


def settings(
    processing: ProcessingSettings, llm: FakeLLMClient | None = None
) -> StepSettings:
    return StepSettings(source="unused", processing=processing, cfg=CFG, llm=llm)


@pytest.fixture(scope="session")
def silent_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 20 s 320x240 video with a silent track: a still grey picture for
    STILL_S, then ffmpeg's moving testsrc2 pattern for MOVING_S."""
    path = tmp_path_factory.mktemp("silent") / "silent.mp4"
    size = "size=320x240:rate=30"
    run_ffmpeg(
        ["-f", "lavfi", "-i", f"color=c=gray:{size}:duration={STILL_S}"]
        + ["-f", "lavfi", "-i", f"testsrc2={size}:duration={MOVING_S}"]
        + ["-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000"]
        + ["-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]"]
        + ["-map", "[v]", "-map", "2:a", "-t", f"{STILL_S + MOVING_S}"]
        + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path]
    )
    return path


@pytest.fixture
def silent_job(silent_video: Path, tmp_path: Path) -> Path:
    """A job of silent_video after ingest, transcribe (no speech) and
    signals: a scene cut where the pattern starts and a cheer in it."""
    job = tmp_path / "job"
    ingest.run(job, StepSettings(source=str(silent_video)))
    duration = load_meta(job).duration
    write_json(
        job / TRANSCRIPT, Transcript(language="en", duration=duration, segments=[])
    )
    events = [
        SignalEvent(kind="scene_cut", start=STILL_S, end=STILL_S, intensity=1),
        SignalEvent(kind="cheer", start=12.0, end=16.0, intensity=0.8),
        SignalEvent(kind="silence", start=0.0, end=STILL_S, intensity=1),
    ]
    write_json(job / SIGNALS, SignalList(events))
    return job


@pytest.fixture
def vlm(
    monkeypatch: pytest.MonkeyPatch, respx_mock: respx.MockRouter
) -> Iterator[respx.Route]:
    """The vision model engine installed, on a fake Ollama server that
    answers CAPTIONS; returns its chat route."""
    use_server(monkeypatch)
    engines.clear_cache()
    route = mock_ollama(respx_mock, CAPTIONS)
    yield route
    engines.clear_cache()


def candidates(job: Path) -> list[ClipCandidate]:
    return CandidateList.model_validate_json((job / CANDIDATES).read_bytes()).clips


def reply(start: float, end: float) -> str:
    """An LLM reply with one wordless clip from start to end seconds."""
    clip = {
        "start": start,
        "end": end,
        "title": "Shapes burst onto the screen",
        "hook_text": "Wait for it",
        "description": "Grey, then colour.",
        "hashtags": ["colour", "shapes", "satisfying"],
        "emphasis_words": [],
        "reason": "The cut to moving shapes and the cheer.",
        "hook": 80,
        "flow": 70,
        "value": 60,
        "trend": 65,
    }
    return json.dumps({"clips": [clip]})


def test_motion_energy_per_second_on_the_fixture(sample_mp4: Path) -> None:
    track = measure_motion(sample_mp4, 2.0, 12.5)

    assert track.start == 2.0
    assert len(track.scores) == 11
    assert all(0 < score < MOTION_FLOOR for score in track.scores)


def test_motion_is_zero_when_still_and_high_when_moving(silent_video: Path) -> None:
    track = measure_motion(silent_video, 0.0, STILL_S + MOVING_S)

    assert track.scores[:10] == [0.0] * 10
    assert all(score >= MOTION_FLOOR for score in track.scores[10:])
    [span] = motion_spans(track)
    assert (span.start, span.end) == (STILL_S, STILL_S + MOVING_S)
    assert 0.5 < span.level < 1


def test_motion_spans_join_short_gaps_and_ignore_a_quiet_video() -> None:
    track = MotionTrack(start=100.0, scores=[0, 0.05, 0, 0.1, 0, 0, 0.04, 0, 0])

    assert motion_spans(track) == [
        MotionSpan(101.0, 104.0, 0.5),
        MotionSpan(106.0, 107.0, 0.4),
    ]
    assert motion_spans(MotionTrack(start=0, scores=[0.012, 0.019, 0.01])) == []
    assert motion_spans(MotionTrack(start=0, scores=[])) == []


def test_timeline_lines_by_time() -> None:
    events = [
        SignalEvent(kind="music", start=30.0, end=45.5, intensity=0.6),
        SignalEvent(kind="energy_peak", start=3.0, end=4.0, intensity=0.9),
        SignalEvent(kind="scene_cut", start=5.0, end=5.0, intensity=1),
        SignalEvent(kind="laugh", start=6.0, end=8.1, intensity=0.85),
    ]
    spans = [MotionSpan(5.0, 70.0, 0.75)]
    captions = [FrameCaption(time=5.2, reason="scene_cut", caption=" A  dog\n runs. ")]

    lines = timeline_lines(events, spans, captions, end=65.0)

    assert [line.text for line in lines] == [
        "[00:05.0] SCENE CUT",
        "[00:05.0-01:05.0] MOTION 0.75",
        "[00:05.2] FRAME: A dog runs.",
        "[00:06.0-00:08.1] LAUGH 0.85",
        "[00:30.0-00:45.5] MUSIC 0.60",
    ]
    assert [line.start for line in lines] == [5.0, 5.0, 5.2, 6.0, 30.0]


def test_system_prompt_explains_the_timeline_only_with_clip_anything() -> None:
    heading = "## What is seen and heard"

    assert heading in system_prompt("podcast", ANYTHING, CFG)
    assert heading not in system_prompt("podcast", ProcessingSettings(), CFG)
    captions_only = ProcessingSettings(clip_anything=True, clipping="captions_only")
    assert heading not in system_prompt("podcast", captions_only, CFG)
    assert "\n\n\n" not in system_prompt("podcast", ProcessingSettings(), CFG)


def test_visuals_does_nothing_without_clip_anything(silent_job: Path) -> None:
    progress: list[float] = []
    step = StepSettings(source="unused", on_progress=progress.append)

    assert visuals.run(silent_job, step) == silent_job / MOTION
    assert not (silent_job / MOTION).exists()
    assert not (silent_job / FRAME_CAPTIONS).exists()
    assert progress == [1.0]


def test_silent_video_yields_clips(silent_job: Path, vlm: respx.Route) -> None:
    progress: list[float] = []
    step = StepSettings(
        source="unused", processing=ANYTHING, on_progress=progress.append
    )
    visuals.run(silent_job, step)
    llm = FakeLLMClient(reply(STILL_S, STILL_S + MOVING_S))
    enrich.run(silent_job, settings(ANYTHING))
    assert (silent_job / "enriched.txt").read_text() == ""

    curate.run(silent_job, settings(ANYTHING, llm))
    score.run(silent_job, settings(ANYTHING))
    snap.run(silent_job, settings(ANYTHING))

    captions = FrameCaptionList.model_validate_json(
        (silent_job / FRAME_CAPTIONS).read_bytes()
    )
    assert [(c.time, c.reason) for c in captions.captions] == [
        (0.0, "interval"),
        (10.2, "scene_cut"),
    ]
    assert vlm.call_count == 2
    assert progress[0] == pytest.approx(visuals.MOTION_SHARE) and progress[-1] == 1
    [(system, user)] = llm.calls
    assert "## What is seen and heard" in system
    lines = user.splitlines()
    assert lines[0] == "[00:00.0] FRAME: A plain grey screen."
    assert lines[1] == "[00:10.0] SCENE CUT"
    assert lines[2].startswith("[00:10.0-00:20.0] MOTION 0.")
    assert lines[3:] == [
        "[00:10.2] FRAME: Colourful shapes move across it.",
        "[00:12.0-00:16.0] CHEER 0.80",
    ]
    snapped = ScoredList.model_validate_json((silent_job / SNAPPED).read_bytes())
    assert [(c.start, c.end) for c in snapped.clips] == [(STILL_S, STILL_S + MOVING_S)]
    assert new_clip_cuts(silent_job, [(STILL_S, 20.0)], ANYTHING) == [[]]
    assert new_clip_cuts(silent_job, [(STILL_S, 20.0)], ProcessingSettings()) != [[]]


def test_without_clip_anything_a_silent_video_has_no_clips(silent_job: Path) -> None:
    llm = FakeLLMClient(reply(STILL_S, STILL_S + MOVING_S))
    off = ProcessingSettings()
    enrich.run(silent_job, settings(off))

    curate.run(silent_job, settings(off, llm))

    assert llm.calls == []
    assert candidates(silent_job) == []


def test_clip_anything_without_a_vision_model_uses_motion_and_sound(
    silent_job: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engines, "is_installed", lambda name, refresh=False: False)
    visuals.run(silent_job, settings(ANYTHING))
    llm = FakeLLMClient(reply(STILL_S, STILL_S + MOVING_S))
    enrich.run(silent_job, settings(ANYTHING))

    curate.run(silent_job, settings(ANYTHING, llm))

    assert (silent_job / MOTION).is_file()
    assert not (silent_job / FRAME_CAPTIONS).exists()
    [(_, user)] = llm.calls
    assert "FRAME" not in user and "MOTION" in user and "CHEER 0.80" in user
    assert len(candidates(silent_job)) == 1
