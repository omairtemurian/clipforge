"""Tests for ClaudeCodeClient (LLM_PROVIDER=claude_code): the command line it
runs, the outputs it reads (a recorded `claude -p` output and shapes built on
it; the subprocess is faked), the version check, and curate's retry with it.
The live test is opt-in (`pytest -m live`) and needs a logged-in Claude Code."""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
from clipforge import config, usage
from clipforge.asset_rows import UsageRecordRow
from clipforge.config import Settings
from clipforge.engines.checks import ClaudeCodeEngine
from clipforge.llm import (
    ClaudeCodeClient,
    LLMClient,
    LLMError,
    create_client,
    model_of,
    reply_json,
)
from clipforge.llm_claude_code import (
    MAX_ARG_BYTES,
    NOT_LOGGED_IN,
    TIMEOUT_S,
    claude_code_version,
)
from clipforge.models import CandidateList
from clipforge.pipeline.curate import Window, ask_window
from clipforge.pipeline.enrich import PromptLine
from fakes import FIXTURES, LLM_RESPONSE
from sqlalchemy import Engine
from sqlmodel import Session, select

SYSTEM = "You find clips in a transcript. Answer with JSON only."
USER = "[00:01.0-00:04.2] S0: Hello there."
CLIPS_JSON = LLM_RESPONSE.read_text(encoding="utf-8").strip()
# What Claude Code 2.1.284 printed on this machine with an expired login.
NOT_LOGGED_IN_OUTPUT = (FIXTURES / "claude_code_not_logged_in.json").read_text()


def success(result: str, *, tokens: tuple[int, int] = (40, 260)) -> str:
    """A successful `claude -p --output-format json` output: the recorded
    one with is_error false, the reply text and token counts."""
    output = json.loads(NOT_LOGGED_IN_OUTPUT)
    output.update(is_error=False, result=result, terminal_reason="completed")
    output["usage"].update(input_tokens=tokens[0], output_tokens=tokens[1])
    return json.dumps(output)


class FakeClaude:
    """A stand-in for subprocess.run: records each call and prints the next
    output, or raises the next exception."""

    def __init__(self, *outputs: str | BaseException, returncode: int = 0) -> None:
        self.outputs = list(outputs)
        self.returncode = returncode
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(
        self, argv: list[str], **options: Any
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((argv, options))
        assert Path(options["cwd"]).is_dir()
        assert list(Path(options["cwd"]).iterdir()) == []
        output = self.outputs.pop(0)
        if isinstance(output, BaseException):
            raise output
        return subprocess.CompletedProcess(argv, self.returncode, output, "")


def client(fake: FakeClaude) -> ClaudeCodeClient:
    return ClaudeCodeClient("/opt/bin/claude", "sonnet", run=fake)


def test_the_command_line_is_exactly_the_documented_one() -> None:
    fake = FakeClaude(success('{"ok": true}'))

    assert client(fake).complete_json(SYSTEM, USER) == '{"ok": true}'

    ((argv, options),) = fake.calls
    assert argv == [
        "/opt/bin/claude",
        "-p",
        USER,
        "--output-format",
        "json",
        "--model",
        "sonnet",
        "--system-prompt",
        SYSTEM,
        "--strict-mcp-config",
        "--tools",
        "",
        "--no-session-persistence",
    ]
    assert options["stdin"] is subprocess.DEVNULL
    assert "input" not in options
    assert options["timeout"] == TIMEOUT_S == 300
    assert options["capture_output"] and options["text"]
    assert not Path(options["cwd"]).exists()


def test_a_prompt_too_long_for_the_command_line_goes_on_stdin() -> None:
    fake = FakeClaude(success("{}"))
    long_prompt = "x" * (MAX_ARG_BYTES + 1)

    client(fake).complete_json(SYSTEM, long_prompt)

    ((argv, options),) = fake.calls
    assert argv[:3] == ["/opt/bin/claude", "-p", "--output-format"]
    assert long_prompt not in argv
    assert options["input"] == long_prompt
    assert "stdin" not in options


def test_a_fenced_reply_is_returned_as_is_for_reply_json() -> None:
    fake = FakeClaude(success('```json\n{"answer": 4}\n```'))

    reply = client(fake).complete_json(SYSTEM, USER)

    assert json.loads(reply_json(reply)) == {"answer": 4}


def test_tokens_are_recorded(engine: Engine) -> None:
    fake = FakeClaude(success("{}", tokens=(40, 260)))

    with usage.recording(engine, None):
        client(fake).complete_json(SYSTEM, USER)

    with Session(engine) as session:
        (record,) = session.exec(select(UsageRecordRow)).all()
    assert (record.kind, record.units) == (usage.LLM_TOKENS, 300)


def test_the_recorded_login_error_asks_to_log_in() -> None:
    fake = FakeClaude(NOT_LOGGED_IN_OUTPUT)

    with pytest.raises(LLMError) as raised:
        client(fake).complete_json(SYSTEM, USER)

    assert str(raised.value) == (
        f"claude_code: {NOT_LOGGED_IN} (Failed to authenticate: OAuth session "
        "expired and could not be refreshed)"
    )


def test_another_error_result_is_reported_as_is() -> None:
    output = json.loads(NOT_LOGGED_IN_OUTPUT)
    output["result"] = "Model 'sonet' not found"

    with pytest.raises(LLMError, match="^claude_code: Model 'sonet' not found$"):
        client(FakeClaude(json.dumps(output))).complete_json(SYSTEM, USER)


@pytest.mark.parametrize(
    "stdout", ["", "Error: unknown option '--tools'", '{"type": "result", "is_err']
)
def test_output_that_is_not_a_result_object_is_an_error(stdout: str) -> None:
    fake = FakeClaude(stdout, returncode=1)

    with pytest.raises(LLMError, match=r"^claude_code: unexpected output \(exit 1\)"):
        client(fake).complete_json(SYSTEM, USER)


def test_a_timeout_and_a_missing_program_are_errors() -> None:
    timeout = subprocess.TimeoutExpired(["claude"], TIMEOUT_S)
    missing = FileNotFoundError(2, "No such file or directory")

    with pytest.raises(LLMError, match=r"no reply in 300s \(sonnet\)"):
        client(FakeClaude(timeout)).complete_json(SYSTEM, USER)
    with pytest.raises(LLMError, match="cannot run /opt/bin/claude .*CLAUDE_CODE_BIN"):
        client(FakeClaude(missing)).complete_json(SYSTEM, USER)


def test_create_client_and_model_of_use_the_claude_code_settings() -> None:
    cfg = Settings(
        _env_file=None,
        llm_provider="claude_code",
        claude_code_bin="/usr/local/bin/claude",
        claude_code_model="opus",
    )

    made = create_client(cfg)

    assert isinstance(made, ClaudeCodeClient) and isinstance(made, LLMClient)
    assert (made.binary, made.model) == ("/usr/local/bin/claude", "opus")
    assert model_of(cfg) == "opus"
    defaults = Settings(_env_file=None)
    assert (defaults.claude_code_bin, defaults.claude_code_model) == (
        "claude",
        "sonnet",
    )
    assert defaults.llm_provider == "copilot"


def test_curate_retries_an_invalid_claude_code_reply() -> None:
    fake = FakeClaude(
        success(f"Here are the clips:\n```json\n{CLIPS_JSON}\n```"),
        success(f"```json\n{CLIPS_JSON}\n```"),
    )
    window = Window(0, 600, [PromptLine(0.5, "[00:00.5-00:01.4] S0: Hi everyone.")])

    clips = ask_window(client(fake), "system", window)

    assert clips == CandidateList.model_validate_json(CLIPS_JSON).clips
    assert len(fake.calls) == 2
    retry = fake.calls[1][0][2]
    assert "Your previous reply for this transcript was not valid" in retry


def test_the_version_is_the_first_word_of_claude_version() -> None:
    def run(argv: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        assert argv == ["claude", "--version"]
        return subprocess.CompletedProcess(argv, 0, "2.1.284 (Claude Code)\n", "")

    assert claude_code_version("claude", run) == "2.1.284"


def test_the_engine_reports_a_missing_program(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = Settings(_env_file=None, claude_code_bin="/nonexistent/claude")
    monkeypatch.setattr(config, "settings", cfg)

    found = ClaudeCodeEngine("claude_code", "Claude").install_check()

    assert not found.installed
    assert found.error == "/nonexistent/claude is not installed (Claude Code)"


@pytest.mark.live
def test_claude_code_live_answers_with_json() -> None:
    """Opt-in (`pytest -m live`, with Claude Code logged in): the default
    model returns valid JSON."""
    if shutil.which(config.settings.claude_code_bin) is None:
        pytest.skip("Claude Code is not installed")
    cfg = Settings(llm_provider="claude_code")

    reply = create_client(cfg).complete_json(
        "You are a calculator. Answer with one JSON object only.",
        'What is 2 + 2? Answer as {"answer": <number>}.',
    )

    assert json.loads(reply_json(reply)) == {"answer": 4}
