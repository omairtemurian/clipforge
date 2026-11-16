"""Fixtures shared by every backend test: the committed media fixtures, a
SQLite database in a temporary data directory and the downloaded YAMNet and
face models.

Tests marked live call real services (network, credentials); they are
skipped unless selected with `pytest -m live`.
"""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from clipforge import config
from clipforge.config import Settings
from clipforge.db import create_db_engine, migrate
from clipforge.llm_responses import clear_model_cache
from clipforge.model_files import (
    missing_face_models,
    missing_yamnet_files,
    yamnet_model_dir,
)
from clipforge.pipeline.yamnet import Yamnet, load_yamnet
from clipforge.proedit.critic.capability import clear_vision_cache
from engine_probes import missing_reason
from sqlalchemy import Engine

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODELS_DIR = Path(__file__).resolve().parents[2] / "models"


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip the live tests unless the -m expression names them, and the
    engine_* tests of engines that are not installed (see engine_probes)."""
    live_selected = "live" in config.getoption("markexpr")
    skip_live = pytest.mark.skip(
        reason="calls a real service; run with `pytest -m live`"
    )
    for item in items:
        if not live_selected and item.get_closest_marker("live") is not None:
            item.add_marker(skip_live)
        for marker in item.iter_markers():
            reason = missing_reason(marker.name)
            if reason is not None:
                item.add_marker(pytest.mark.skip(reason=f"{marker.name}: {reason}"))


YTDLP_COOKIE_SETTINGS = ("ytdlp_cookies_from_browser", "ytdlp_cookies_file")


@pytest.fixture(autouse=True)
def no_browser_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let yt-dlp read the owner's browser cookies (a .env.local may
    set them): the environment, which wins over .env.local, clears them."""
    for name in YTDLP_COOKIE_SETTINGS:
        monkeypatch.setenv(name.upper(), "")
    cleared = dict.fromkeys(YTDLP_COOKIE_SETTINGS, "")
    monkeypatch.setattr(config, "settings", config.settings.model_copy(update=cleared))


@pytest.fixture(autouse=True)
def no_notification_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never email or show on the desktop a test's notifications (a .env.local
    may set SMTP_HOST or DESKTOP_NOTIFICATIONS): the environment, which wins
    over .env.local, turns both off."""
    monkeypatch.setenv("SMTP_HOST", "")
    monkeypatch.setenv("DESKTOP_NOTIFICATIONS", "false")
    off = {"smtp_host": "", "desktop_notifications": False}
    monkeypatch.setattr(config, "settings", config.settings.model_copy(update=off))


@pytest.fixture(autouse=True)
def fresh_copilot_models() -> Iterator[None]:
    """Start and end every test with no cached Copilot model list and no
    cached vision probe answer (Pro Edit critic)."""
    clear_model_cache()
    clear_vision_cache()
    yield
    clear_model_cache()
    clear_vision_cache()


@pytest.fixture(scope="session")
def sample_mp4() -> Path:
    """The committed 60 s sample video (do not modify it)."""
    return FIXTURES / "sample.mp4"


@pytest.fixture(scope="session")
def expected() -> dict[str, Any]:
    """The parsed expected.json: ground truth about sample.mp4 (read-only)."""
    data: dict[str, Any] = json.loads((FIXTURES / "expected.json").read_text())
    return data


@pytest.fixture
def data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A data directory that config.settings points at but that does not exist.

    config.settings also takes the models from the project's models/, so that
    runs of the whole pipeline find YAMNet from any working directory.
    """
    path = tmp_path / "data"
    monkeypatch.setattr(
        config, "settings", Settings(data_dir=path, models_dir=MODELS_DIR)
    )
    return path


@pytest.fixture(scope="module")
def module_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """data_dir for module-scoped fixtures (renders that cache files there)."""
    path = tmp_path_factory.mktemp("module") / "data"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            config, "settings", Settings(data_dir=path, models_dir=MODELS_DIR)
        )
        yield path


@pytest.fixture
def blank_engine(data_dir: Path) -> Iterator[Engine]:
    """An engine for an empty database in the configured data directory."""
    engine = create_db_engine()
    yield engine
    engine.dispose()


@pytest.fixture
def engine(blank_engine: Engine) -> Engine:
    """An engine for a database with every migration applied."""
    migrate(blank_engine)
    return blank_engine


@pytest.fixture
def rows(blank_engine: Engine) -> Callable[[str], list[tuple[Any, ...]]]:
    """Return a function that runs raw SQL on the test database."""

    def fetch(sql: str) -> list[tuple[Any, ...]]:
        with blank_engine.connect() as conn:
            return [tuple(row) for row in conn.exec_driver_sql(sql)]

    return fetch


@pytest.fixture(scope="session")
def yamnet_cfg() -> Settings:
    """Settings that use the downloaded YAMNet model; skips if it is missing."""
    cfg = Settings(models_dir=MODELS_DIR)
    model_dir = yamnet_model_dir(cfg)
    if missing_yamnet_files(model_dir):
        pytest.skip(
            f"the YAMNet model is not downloaded to {model_dir}; run `make setup`"
        )
    return cfg


@pytest.fixture(scope="session")
def face_cfg() -> Settings:
    """Settings that use the downloaded face models; skips if one is missing."""
    cfg = Settings(models_dir=MODELS_DIR)
    missing = missing_face_models(cfg)
    if missing:
        pytest.skip(f"the face model {missing[0]} is not downloaded; run `make setup`")
    return cfg


@pytest.fixture(scope="session")
def yamnet_model(yamnet_cfg: Settings) -> Yamnet:
    """The downloaded YAMNet model, loaded once (skips if it is missing)."""
    return load_yamnet(yamnet_cfg)
