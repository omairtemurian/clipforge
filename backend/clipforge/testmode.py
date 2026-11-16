"""Test mode of `clipforge run`: recorded inputs instead of whisper and the LLM.

With the environment variable CLIPFORGE_TEST_MODE=1 and --fixtures-dir DIR,
a run takes DIR/transcript.json as the transcript and answers every LLM
prompt with the text of DIR/llm_response.json, so it needs neither the
whisper model nor LLM credentials. The other steps and the render run for
real. Test mode needs both switches: either one alone is an error, so it
never turns on by accident.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx

ENV_VAR = "CLIPFORGE_TEST_MODE"
TRANSCRIPT_FILE = "transcript.json"
LLM_RESPONSE_FILE = "llm_response.json"


@dataclass(frozen=True)
class RecordedInputs:
    """The files that test mode uses in place of transcribing and asking the LLM."""

    transcript: Path
    llm_response: Path


class RecordedLLM:
    """An LLM client that answers every prompt with the text of one file."""

    def __init__(self, reply: Path) -> None:
        self.reply = reply

    def complete_json(self, system: str, user: str) -> str:
        """Return the text of the reply file, whatever the prompt."""
        return self.reply.read_text(encoding="utf-8")


def offline_llm_transport() -> httpx.BaseTransport:
    """Return a transport for the Settings page's LLM requests (the model list
    and the connection test) that answers from memory, so test mode never
    reaches a provider: any model list has two models, any chat request is
    answered."""

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/tags"):
            return httpx.Response(200, json={"models": [{"name": "llama3:latest"}]})
        if request.url.path.endswith("/models"):
            models = [{"id": "test-model-a"}, {"id": "test-model-b"}]
            return httpx.Response(200, json={"data": models})
        reply = {"choices": [{"message": {"content": '{"ok": true}'}}]}
        return httpx.Response(200, json=reply)

    return httpx.MockTransport(answer)


def recorded_inputs(
    fixtures_dir: Path | None, environ: Mapping[str, str] = os.environ
) -> RecordedInputs | None:
    """Return the recorded inputs in fixtures_dir if test mode is on, else None.

    Test mode is on when environ sets CLIPFORGE_TEST_MODE to "1" and
    fixtures_dir is given. Raises ValueError if only one of the two is set, or
    if fixtures_dir lacks transcript.json or llm_response.json.
    """
    enabled = environ.get(ENV_VAR) == "1"
    if fixtures_dir is None:
        if enabled:
            raise ValueError(f"{ENV_VAR}=1 needs --fixtures-dir")
        return None
    if not enabled:
        raise ValueError(f"--fixtures-dir needs {ENV_VAR}=1")
    inputs = RecordedInputs(
        transcript=fixtures_dir / TRANSCRIPT_FILE,
        llm_response=fixtures_dir / LLM_RESPONSE_FILE,
    )
    for path in (inputs.transcript, inputs.llm_response):
        if not path.is_file():
            raise ValueError(f"test mode needs {path}, which is not a file")
    return inputs
