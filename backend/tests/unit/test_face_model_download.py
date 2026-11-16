"""Tests of the face model download (model_files.download_face_model): the
face detector, face landmarker and person detector reframe runs.

httpx.MockTransport answers the requests, so nothing is fetched; the real
download is checked by hand (see docs/progress.md), and the slow test checks
the models that `make setup` downloaded.
"""

import hashlib
from pathlib import Path

import httpx
import pytest
from clipforge import model_files
from clipforge.config import Settings
from clipforge.model_files import (
    FACE_DETECTOR,
    FACE_MODELS,
    download_face_model,
    face_model_path,
    file_sha256,
    missing_face_models,
)

MODEL = b"a face model"


class FakeServer:
    """Answers every request with status and body; records the URLs asked for."""

    def __init__(self, status: int = 200, body: bytes = MODEL) -> None:
        self.status, self.body = status, body
        self.urls: list[str] = []

    def transport(self) -> httpx.MockTransport:
        """Return a transport that sends the requests to this server."""
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        """Record request's URL and answer it."""
        self.urls.append(str(request.url))
        return httpx.Response(self.status, content=self.body)


@pytest.fixture
def cfg(tmp_path: Path) -> Settings:
    """Settings with the models in tmp_path/models."""
    return Settings(models_dir=tmp_path / "models")


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make MODEL's sha256 the pinned one of each face model."""
    sha256 = hashlib.sha256(MODEL).hexdigest()
    models = tuple(model._replace(sha256=sha256) for model in FACE_MODELS)
    monkeypatch.setattr(model_files, "FACE_MODELS", models)


@pytest.mark.usefixtures("pinned")
def test_the_face_models_are_downloaded_from_their_pinned_urls(
    cfg: Settings,
) -> None:
    server = FakeServer()
    assert len(missing_face_models(cfg)) == 3

    directory = download_face_model(cfg, transport=server.transport())

    names = [
        "blaze_face_full_range.tflite",
        "face_landmarker.task",
        "efficientdet_lite0.tflite",
    ]
    assert directory == cfg.models_dir / "face"
    assert [model.name for model in FACE_MODELS] == names
    assert server.urls == [model.url for model in FACE_MODELS]
    assert sorted(path.name for path in directory.iterdir()) == sorted(names)
    assert all((directory / name).read_bytes() == MODEL for name in names)
    assert missing_face_models(cfg) == []
    assert FACE_DETECTOR.url == (
        "https://storage.googleapis.com/mediapipe-models/face_detector/"
        "blaze_face_full_range/float16/1/blaze_face_full_range.tflite"
    )


@pytest.mark.usefixtures("pinned")
def test_a_face_model_that_is_there_is_downloaded_again_only_when_forced(
    cfg: Settings,
) -> None:
    path = face_model_path(cfg)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"an old model")
    server = FakeServer()

    download_face_model(cfg, transport=server.transport())
    assert path.read_bytes() == b"an old model"
    assert server.urls == [model.url for model in FACE_MODELS[1:]]

    server.urls.clear()
    download_face_model(cfg, force=True, transport=server.transport())
    assert (server.urls, path.read_bytes()) == ([m.url for m in FACE_MODELS], MODEL)


def test_a_face_model_with_another_sha256_is_an_error_and_not_kept(
    cfg: Settings,
) -> None:
    path = face_model_path(cfg)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"an old model")
    actual = hashlib.sha256(MODEL).hexdigest()

    with pytest.raises(RuntimeError) as error:
        download_face_model(cfg, force=True, transport=FakeServer().transport())

    expected = FACE_DETECTOR.sha256
    message = f"{FACE_DETECTOR.url}: sha256 is {actual}, expected {expected}"
    assert str(error.value) == message
    assert list(path.parent.iterdir()) == [path]
    assert path.read_bytes() == b"an old model"


def test_a_failed_face_model_download_is_an_http_error(cfg: Settings) -> None:
    server = FakeServer(status=404, body=b"not found")

    with pytest.raises(httpx.HTTPStatusError, match="404 Not Found"):
        download_face_model(cfg, transport=server.transport())

    assert list(face_model_path(cfg).parent.iterdir()) == []


@pytest.mark.slow
def test_the_downloaded_face_models_have_the_pinned_sha256(
    face_cfg: Settings,
) -> None:
    for model in FACE_MODELS:
        assert file_sha256(face_model_path(face_cfg, model)) == model.sha256
