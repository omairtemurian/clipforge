"""Settings endpoints with LLM_PROVIDER=claude_code: the program and model
are saved like the other settings, and the connection test runs the program
(here a stand-in script that prints a recorded `claude -p` output)."""

import json
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge import config
from clipforge.api.app import create_app
from clipforge.llm_claude_code import NOT_LOGGED_IN
from fakes import FIXTURES
from fastapi.testclient import TestClient

NOT_LOGGED_IN_OUTPUT = FIXTURES / "claude_code_not_logged_in.json"


@pytest.fixture
def client(data_dir: Path, work_in_tmp: Path) -> Iterator[TestClient]:
    app = create_app(run_worker=False, caption_previews=False)
    with TestClient(app) as test_client:
        yield test_client


def fake_claude(folder: Path, output: Path) -> Path:
    """A program that saves its arguments in args.json and prints output."""
    program = folder / "claude"
    save_args = f'json.dump(sys.argv[1:], open("{folder}/args.json", "w"))'
    program.write_text(
        f"#!/bin/sh\npython3 -c 'import json, sys; {save_args}' \"$@\"\n"
        f'cat "{output}"\n'
    )
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    return program


def test_the_claude_code_settings_are_saved(
    client: TestClient, tmp_path: Path, work_in_tmp: Path
) -> None:
    program = fake_claude(tmp_path, NOT_LOGGED_IN_OUTPUT)

    body = client.put(
        "/api/settings",
        json={
            "llm_provider": "claude_code",
            "claude_code_bin": str(program),
            "claude_code_model": "opus",
        },
    ).json()

    assert (body["claude_code_bin"], body["claude_code_model"]) == (
        str(program),
        "opus",
    )
    assert config.settings.llm_provider == "claude_code"
    assert 'CLAUDE_CODE_MODEL="opus"' in (work_in_tmp / ".env.local").read_text()


def test_a_program_that_does_not_exist_is_rejected(client: TestClient) -> None:
    response = client.put(
        "/api/settings", json={"claude_code_bin": "/nonexistent/claude"}
    )

    assert_error(response, 422, "validation_error")


def test_test_llm_runs_claude_code_and_reads_its_reply(
    client: TestClient, tmp_path: Path
) -> None:
    output = json.loads(NOT_LOGGED_IN_OUTPUT.read_text())
    output.update(is_error=False, result='```json\n{"ok": true}\n```')
    reply = tmp_path / "reply.json"
    reply.write_text(json.dumps(output))
    program = fake_claude(tmp_path, reply)

    body = client.post(
        "/api/settings/test-llm",
        json={"llm_provider": "claude_code", "claude_code_bin": str(program)},
    ).json()

    assert body == {
        "ok": True,
        "provider": "claude_code",
        "model": "sonnet",
        "message": '```json {"ok": true} ```',
    }
    args = json.loads((tmp_path / "args.json").read_text())
    assert args[0] == "-p" and args[2:4] == ["--output-format", "json"]
    assert args[-1] == "--no-session-persistence"


def test_test_llm_shows_the_login_hint(client: TestClient, tmp_path: Path) -> None:
    program = fake_claude(tmp_path, NOT_LOGGED_IN_OUTPUT)

    body = client.post(
        "/api/settings/test-llm",
        json={"llm_provider": "claude_code", "claude_code_bin": str(program)},
    ).json()

    assert body["ok"] is False
    assert NOT_LOGGED_IN in body["message"]
