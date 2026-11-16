"""The transcribe_backend setting on the Settings page (TASK-197)."""

from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge import config
from clipforge.pipeline import transcribe_mlx
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def no_mlx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make this machine one without MLX, whatever the test machine is."""
    monkeypatch.setattr(transcribe_mlx, "apple_silicon", lambda: False)


def test_get_shows_the_setting_and_the_backend_in_use(client: TestClient) -> None:
    config.settings = config.Settings(data_dir=config.settings.data_dir)

    body = client.get("/api/settings").json()

    assert body["transcribe_backend"] == "auto"
    assert body["transcribe_backend_active"] == "faster_whisper"


def test_get_shows_mlx_when_it_is_chosen(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(transcribe_mlx, "apple_silicon", lambda: True)
    monkeypatch.setattr(transcribe_mlx, "mlx_installed", lambda: True)
    cfg = config.Settings(data_dir=config.settings.data_dir, models_dir=tmp_path)
    model_dir = transcribe_mlx.mlx_model_dir(cfg)
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}")
    (model_dir / "weights.npz").write_bytes(b"")
    config.settings = cfg

    body = client.get("/api/settings").json()

    assert body["transcribe_backend_active"] == "mlx"


def test_put_saves_the_backend(client: TestClient, work_in_tmp: Path) -> None:
    response = client.put("/api/settings", json={"transcribe_backend": "mlx"})

    assert response.status_code == 200
    assert response.json()["transcribe_backend"] == "mlx"
    assert response.json()["transcribe_backend_active"] == "faster_whisper"
    assert config.settings.transcribe_backend == "mlx"
    env = (work_in_tmp / ".env.local").read_text().splitlines()
    assert 'TRANSCRIBE_BACKEND="mlx"' in env


def test_put_refuses_an_unknown_backend(client: TestClient, work_in_tmp: Path) -> None:
    response = client.put("/api/settings", json={"transcribe_backend": "cuda"})

    assert_error(response, 422, "validation_error")
    assert not (work_in_tmp / ".env.local").exists()
