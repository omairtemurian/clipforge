"""Tests of the API in test mode: it starts only with both switches, and the
creator watch does not poll."""

import threading
from pathlib import Path

import pytest
from clipforge.api import app as app_module
from clipforge.api.testapp import FIXTURES_DIR_ENV_VAR, create_test_app
from clipforge.testmode import ENV_VAR, RecordedLLM
from fakes import FIXTURES, LLM_RESPONSE
from fastapi.testclient import TestClient

NEEDS_BOTH = (
    "the test server needs CLIPFORGE_TEST_MODE=1 and CLIPFORGE_FIXTURES_DIR=DIR"
)


@pytest.mark.parametrize(
    "environ",
    [
        {},
        {ENV_VAR: "1"},
        {FIXTURES_DIR_ENV_VAR: str(FIXTURES)},
        {ENV_VAR: "true", FIXTURES_DIR_ENV_VAR: str(FIXTURES)},
        {ENV_VAR: "1", FIXTURES_DIR_ENV_VAR: ""},
    ],
)
def test_the_test_server_needs_both_switches(environ: dict[str, str]) -> None:
    with pytest.raises(ValueError) as excinfo:
        create_test_app(environ)
    assert str(excinfo.value) == NEEDS_BOTH


def test_the_test_server_needs_the_recorded_files(tmp_path: Path) -> None:
    environ = {ENV_VAR: "1", FIXTURES_DIR_ENV_VAR: str(tmp_path)}
    with pytest.raises(ValueError, match="transcript.json, which is not a file"):
        create_test_app(environ)


def test_the_test_server_gives_its_jobs_the_recorded_inputs(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_module, "ensure_previews", lambda: None)
    environ = {ENV_VAR: "1", FIXTURES_DIR_ENV_VAR: str(FIXTURES)}
    with TestClient(create_test_app(environ)) as client:
        worker = client.app.state.worker  # type: ignore[attr-defined]
        assert worker.transcript == FIXTURES / "transcript.json"
        assert isinstance(worker.llm, RecordedLLM)
        assert worker.llm.reply == LLM_RESPONSE
        assert client.get("/api/projects").json() == []
        threads = {thread.name for thread in threading.enumerate()}
        assert "clipforge-auto-import" not in threads
        assert "clipforge-twitch-watch" not in threads
