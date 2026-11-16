"""The Claude subscription client of clipforge.llm (LLM_PROVIDER=claude_code).

Runs the Claude Code CLI, logged in with the owner's Claude subscription, as
a one-shot subprocess (flags checked with `claude --help`, Claude Code
2.1.284, 2026-10-31):

    claude -p <prompt> --output-format json --model <model>
        --system-prompt <system> --strict-mcp-config --tools ""
        --no-session-persistence

in an empty temporary directory (no CLAUDE.md, settings or hooks of a
project load) with stdin closed. A prompt too long for the command line is
sent on stdin instead (`claude -p` reads it from there). The output is one
JSON object: {"type": "result", "is_error": bool, "result": "<reply text>",
"usage": {"input_tokens", "output_tokens", ...}, ...}; is_error is true when
Claude Code could not answer (for example, not logged in).
"""

import logging
import subprocess
import tempfile
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from clipforge import usage
from clipforge.llm_http import LLMError

__all__ = [
    "MAX_ARG_BYTES",
    "NOT_LOGGED_IN",
    "TIMEOUT_S",
    "ClaudeCodeClient",
    "ClaudeCodeResult",
    "claude_code_version",
]

logger = logging.getLogger(__name__)

PROVIDER = "claude_code"
# A clip-picking call reads a transcript window and can take minutes.
TIMEOUT_S = 300.0
VERSION_TIMEOUT_S = 15.0
# Longer prompts go on stdin: macOS limits a command line to about 1 MB.
MAX_ARG_BYTES = 100_000
NOT_LOGGED_IN = (
    "Claude Code is not logged in. Run `claude` in a terminal and log in, then retry."
)
# Words of Claude Code's results that mean the login is missing or expired.
AUTH_WORDS = ("authenticat", "log in", "login", "oauth", "not logged")

Runner = Callable[..., subprocess.CompletedProcess[str]]


class _Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ClaudeCodeResult(BaseModel):
    """The part of `claude -p --output-format json` output that is used."""

    type: str
    is_error: bool = False
    result: str = ""
    usage: _Usage | None = None


class ClaudeCodeClient:
    """The Claude Code CLI with the subscription it is logged in with."""

    provider = PROVIDER

    def __init__(
        self,
        binary: str,
        model: str,
        *,
        run: Runner = subprocess.run,
        timeout_s: float = TIMEOUT_S,
    ) -> None:
        self.binary = binary or "claude"
        self.model = model
        self.timeout_s = timeout_s
        self._run = run

    def argv(self, system: str, prompt: str | None) -> list[str]:
        """Return the command line; without a prompt, `claude -p` reads it
        from stdin."""
        head = [self.binary, "-p"] + ([prompt] if prompt is not None else [])
        return head + [
            "--output-format",
            "json",
            "--model",
            self.model,
            "--system-prompt",
            system,
            "--strict-mcp-config",
            "--tools",
            "",
            "--no-session-persistence",
        ]

    def complete_json(self, system: str, user: str) -> str:
        """Return the model's reply text to the system prompt and user message;
        record its input and output tokens in the usage meter."""
        on_stdin = len(user.encode()) > MAX_ARG_BYTES
        argv = self.argv(system, None if on_stdin else user)
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="clipforge-claude-") as cwd:
            done = self._call(argv, cwd, user if on_stdin else None)
        logger.info(
            "%s %s replied in %.1fs",
            PROVIDER,
            self.model,
            time.monotonic() - started,
        )
        result = parse_output(done)
        if result.usage is not None:
            usage.record_tokens(result.usage.input_tokens + result.usage.output_tokens)
        return result.result

    def _call(
        self, argv: list[str], cwd: str, stdin: str | None
    ) -> subprocess.CompletedProcess[str]:
        """Run argv in cwd; LLMError when it cannot start or times out."""
        options: dict[str, Any] = {
            "cwd": cwd,
            "capture_output": True,
            "text": True,
            "timeout": self.timeout_s,
        }
        if stdin is None:
            options["stdin"] = subprocess.DEVNULL
        else:
            options["input"] = stdin
        try:
            return self._run(argv, **options)
        except OSError as exc:
            raise LLMError(
                f"{PROVIDER}: cannot run {self.binary} ({exc.strerror}): install "
                "Claude Code or set CLAUDE_CODE_BIN (Settings)"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise LLMError(
                f"{PROVIDER}: no reply in {self.timeout_s:.0f}s ({self.model})"
            ) from exc


def parse_output(done: subprocess.CompletedProcess[str]) -> ClaudeCodeResult:
    """Return the result object of a `claude -p` run; LLMError when the
    output is not one, or when Claude Code reports an error."""
    try:
        result = ClaudeCodeResult.model_validate_json(done.stdout)
    except ValidationError as exc:
        detail = (done.stdout.strip() or done.stderr.strip())[:300]
        raise LLMError(
            f"{PROVIDER}: unexpected output (exit {done.returncode}): {detail}"
        ) from exc
    if result.is_error:
        raise LLMError(_error_message(result.result))
    if result.type != "result":
        raise LLMError(f"{PROVIDER}: unexpected output type {result.type!r}")
    return result


def _error_message(result: str) -> str:
    """The message of an is_error result: the login hint when it is about
    authentication, with Claude Code's own words."""
    if any(word in result.lower() for word in AUTH_WORDS):
        return f"{PROVIDER}: {NOT_LOGGED_IN} ({result})"
    return f"{PROVIDER}: {result or 'Claude Code reported an error'}"


def claude_code_version(binary: str, run: Runner = subprocess.run) -> str:
    """Return the version of the Claude Code CLI (`claude --version` prints
    "2.1.284 (Claude Code)"); LLMError when it is missing or fails."""
    try:
        done = run(
            [binary or "claude", "--version"],
            capture_output=True,
            text=True,
            timeout=VERSION_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise LLMError(f"{PROVIDER}: cannot run {binary} --version: {exc}") from exc
    words = done.stdout.split()
    if done.returncode != 0 or not words:
        raise LLMError(f"{PROVIDER}: {binary} --version failed: {done.stderr.strip()}")
    return words[0]
