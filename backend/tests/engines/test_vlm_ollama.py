"""The Ollama vision engine and the frame captions pass (SPEC-v2 3.2).

Ollama is mocked (httpx.MockTransport or respx) except in the
engine_ollama_vlm test, which captions two frames of the fixture video with
the real local model when one is installed.
"""

import base64
import json
from pathlib import Path

import httpx
import pytest
import respx
from builders import source_meta
from clipforge.engines import InstallStatus
from clipforge.engines.vlm_ollama import OllamaVisionEngine, VisionCaptioner
from clipforge.models import FrameCaptionList, SignalEvent, SignalList
from clipforge.pipeline import frame_captions
from clipforge.pipeline.frame_captions import FrameSample, grab_frame, sample_times
from clipforge.pipeline.step import (
    FRAME_CAPTIONS,
    META,
    SIGNALS,
    SOURCE,
    StepError,
    StepSettings,
    write_json,
)
from vlm_fakes import HOST, mock_ollama, use_server

JPEG_START = b"\xff\xd8"


def fake_ollama(models: dict[str, list[str]]) -> httpx.MockTransport:
    """A fake Ollama server holding models, each with its capabilities."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.34.4"})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": name} for name in models]}
            )
        name = json.loads(request.read())["model"]
        return httpx.Response(200, json={"capabilities": models[name]})

    return httpx.MockTransport(handler)


def engine(models: dict[str, list[str]]) -> OllamaVisionEngine:
    return OllamaVisionEngine("ollama_vlm", "V", fake_ollama(models))


def test_install_check_needs_a_vision_model(monkeypatch: pytest.MonkeyPatch) -> None:
    use_server(monkeypatch)
    found = engine({"a": ["completion"], "b": ["completion", "vision"]})
    assert found.install_check() == InstallStatus(installed=True, version="0.34.4")
    text_only = engine({"a": ["completion"]}).install_check()
    assert text_only.installed is False
    assert text_only.version == "0.34.4"
    assert text_only.error is not None and "vision" in text_only.error


def test_install_check_needs_the_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    models = {"qwen3.5:latest": ["completion", "vision"], "llama3:8b": ["completion"]}
    use_server(monkeypatch, vlm_model="qwen3.5")
    assert engine(models).install_check().installed
    use_server(monkeypatch, vlm_model="llama3:8b")
    status = engine(models).install_check()
    assert status.installed is False
    assert status.error == (
        "VLM_MODEL llama3:8b is not a pulled vision model (ollama pull llama3:8b)"
    )


def test_install_check_reports_a_server_that_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use_server(monkeypatch)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    down = OllamaVisionEngine("ollama_vlm", "V", httpx.MockTransport(refuse))
    status = down.install_check()
    assert status == InstallStatus(
        installed=False, error=f"no Ollama server at {HOST} (ollama serve)"
    )


def test_samples_scene_cuts_and_a_fixed_interval() -> None:
    samples = sample_times(10.0, 40.0, [31.0, 5.0, 21.0, 39.9, 40.0], 10.0)
    assert samples == [
        FrameSample(10.0, "interval"),
        FrameSample(21.2, "scene_cut"),
        FrameSample(31.2, "scene_cut"),
        FrameSample(39.9, "scene_cut"),
    ]
    assert [s.time for s in sample_times(0.0, 25.0, [], 10.0)] == [0.0, 10.0, 20.0]


def test_grab_frame_returns_a_jpeg(sample_mp4: Path) -> None:
    assert grab_frame(sample_mp4, 2.0).startswith(JPEG_START)
    with pytest.raises(StepError, match="frame at 600s"):
        grab_frame(sample_mp4, 600.0)


def make_job(job_dir: Path, video: Path, end: float, cuts: list[float]) -> None:
    """A job after ingest and signals: video as source.mp4, a timeframe
    from 0 to end seconds and scene cuts at cuts."""
    (job_dir / SOURCE).symlink_to(video)
    write_json(job_dir / META, source_meta(0.0, end, duration=60.0))
    events = [
        SignalEvent(kind="scene_cut", start=t, end=t, intensity=1.0) for t in cuts
    ]
    laugh = SignalEvent(kind="laugh", start=1.0, end=2.0, intensity=0.5)
    write_json(job_dir / SIGNALS, SignalList([laugh, *events]))


def test_run_captions_frames_with_timestamps(
    tmp_path: Path,
    sample_mp4: Path,
    monkeypatch: pytest.MonkeyPatch,
    respx_mock: respx.MockRouter,
) -> None:
    use_server(monkeypatch)
    chat = mock_ollama(respx_mock)
    make_job(tmp_path, sample_mp4, 12.0, [5.0])
    progress: list[float] = []
    settings = StepSettings(source="unused", on_progress=progress.append)

    output = frame_captions.run(tmp_path, settings)

    stored = FrameCaptionList.model_validate_json(output.read_text())
    assert output == tmp_path / FRAME_CAPTIONS
    assert stored.model == "qwen3.5-35b-128k:latest"
    assert [(c.time, c.reason, c.caption) for c in stored.captions] == [
        (0.0, "interval", "Frame 0."),
        (5.2, "scene_cut", "Frame 1."),
        (10.0, "interval", "Frame 2."),
    ]
    assert progress == pytest.approx([1 / 3, 2 / 3, 1.0])
    body = json.loads(chat.calls[0].request.content)
    assert body["model"] == "qwen3.5-35b-128k:latest"
    assert body["stream"] is False and body["think"] is False
    image = base64.b64decode(body["messages"][0]["images"][0])
    assert image.startswith(JPEG_START)

    assert frame_captions.run(tmp_path, settings) == output
    assert chat.call_count == 3


def test_run_fails_without_a_vision_model(
    tmp_path: Path, sample_mp4: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_server(monkeypatch)
    make_job(tmp_path, sample_mp4, 12.0, [])
    with respx.mock:
        respx.get(f"{HOST}/api/version").mock(side_effect=httpx.ConnectError("no"))
        with pytest.raises(StepError, match="no Ollama server"):
            frame_captions.run(tmp_path, StepSettings(source="unused"))
    assert not (tmp_path / FRAME_CAPTIONS).exists()


def test_run_fails_on_an_empty_caption(tmp_path: Path, sample_mp4: Path) -> None:
    make_job(tmp_path, sample_mp4, 5.0, [])
    reply = {"message": {"role": "assistant", "content": "  "}}
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=reply))
    captioner = VisionCaptioner(HOST, "m", transport=transport)
    with pytest.raises(StepError, match="empty caption"):
        frame_captions.run(tmp_path, StepSettings(source="unused"), captioner=captioner)


def test_run_needs_the_signals_step(tmp_path: Path, sample_mp4: Path) -> None:
    make_job(tmp_path, sample_mp4, 5.0, [])
    (tmp_path / SIGNALS).unlink()
    with pytest.raises(StepError, match="signals"):
        frame_captions.run(tmp_path, StepSettings(source="unused"))


@pytest.mark.engine_ollama_vlm
def test_real_vision_model_captions_the_fixture(
    tmp_path: Path, sample_mp4: Path
) -> None:
    make_job(tmp_path, sample_mp4, 6.0, [3.0])

    output = frame_captions.run(tmp_path, StepSettings(source="unused"))

    stored = FrameCaptionList.model_validate_json(output.read_text())
    assert stored.model
    assert [(c.time, c.reason) for c in stored.captions] == [
        (0.0, "interval"),
        (3.2, "scene_cut"),
    ]
    assert all(len(c.caption.split()) >= 3 for c in stored.captions)
