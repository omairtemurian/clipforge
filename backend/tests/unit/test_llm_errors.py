"""LLMError (clipforge.llm_http): HTTP errors, unreachable servers and
replies that are not chat answers; credentials never appear in error
messages, tracebacks or logs.
"""

import logging
import socket
import traceback
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from clipforge import llm
from clipforge.llm import (
    CopilotClient,
    LLMError,
    OllamaClient,
    OpenAICompatClient,
)
from clipforge.llm_http import EXCERPT_CHARS
from fakes import FakeLLMServer, ollama_reply, openai_reply

TOKEN = "gho_SecretTestToken0123456789abcdef"
Client = CopilotClient | OpenAICompatClient | OllamaClient
MAKERS: dict[str, Callable[[httpx.BaseTransport], Client]] = {
    "copilot": lambda t: CopilotClient("gpt-4.1", TOKEN, transport=t),
    "openai": lambda t: OpenAICompatClient(
        "https://api.openai.com/v1", TOKEN, "gpt-4.1", transport=t
    ),
    "ollama": lambda t: OllamaClient("http://localhost:11434", "llama3.2", transport=t),
}
MODEL_ERROR = {
    "error": {
        "message": "The requested model is not supported.",
        "code": "model_not_supported",
        "param": "model",
        "type": "invalid_request_error",
    }
}


def call(client: Client) -> LLMError:
    """Return the LLMError that one complete_json call of client raises."""
    with pytest.raises(LLMError) as caught:
        client.complete_json("system prompt", "user prompt")
    return caught.value


@pytest.mark.parametrize("provider", MAKERS)
def test_http_error_has_status_and_body_excerpt(provider: str) -> None:
    server = FakeLLMServer(400, json=MODEL_ERROR)
    client = MAKERS[provider](server.transport)

    error = call(client)

    assert error.status_code == 400
    assert str(error) == (
        f"{provider}: HTTP 400 from {client.url}: "
        '{"error":{"message":"The requested model is not supported.",'
        '"code":"model_not_supported","param":"model",'
        '"type":"invalid_request_error"}}'
    )


def test_error_body_is_one_line_and_cut_to_an_excerpt() -> None:
    server = FakeLLMServer(500, text="Internal\n\n  error: " + "x" * 5000)

    message = str(call(MAKERS["ollama"](server.transport)))

    prefix = "ollama: HTTP 500 from http://localhost:11434/api/chat: "
    assert message.startswith(prefix + "Internal error: xxx")
    assert len(message) == len(prefix) + EXCERPT_CHARS + 1
    assert message.endswith("x…")


def test_empty_error_body() -> None:
    server = FakeLLMServer(502, text="")

    error = call(MAKERS["openai"](server.transport))

    assert error.status_code == 502
    assert str(error) == (
        "openai: HTTP 502 from https://api.openai.com/v1/chat/completions: (empty body)"
    )


@pytest.mark.parametrize(
    ("exception", "reason"),
    [
        (httpx.ConnectError, "[Errno 61] Connection refused"),
        (httpx.ReadTimeout, "timed out"),
    ],
)
def test_unreachable_server_raises(
    exception: type[httpx.TransportError], reason: str
) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise exception(reason, request=request)

    error = call(MAKERS["ollama"](httpx.MockTransport(fail)))

    assert error.status_code is None
    assert str(error) == (
        f"ollama: cannot reach http://localhost:11434/api/chat: {reason}"
    )
    assert isinstance(error.__cause__, exception)


def test_real_connection_refused_raises() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    error = call(OllamaClient(f"http://127.0.0.1:{port}", "llama3.2"))

    url = f"http://127.0.0.1:{port}/api/chat"
    assert str(error).startswith(f"ollama: cannot reach {url}: ")
    assert error.status_code is None


def test_reply_that_is_not_json_raises() -> None:
    """The retired GitHub Models API answers any POST with 200 "OK"."""
    server = FakeLLMServer(200, text="OK")
    client = OpenAICompatClient(
        "https://models.github.ai/inference",
        "pat",
        "openai/gpt-4.1",
        transport=server.transport,
    )

    error = call(client)

    assert error.status_code == 200
    message = str(error)
    assert message.startswith(
        "openai: unexpected reply from "
        "https://models.github.ai/inference/chat/completions (reply: Invalid JSON"
    )
    assert message.endswith("): OK")


@pytest.mark.parametrize(
    ("provider", "reply", "problem"),
    [
        ("copilot", {"choices": []}, "choices: List should have at least 1 item"),
        (
            "openai",
            {"choices": [{"message": {"content": None, "refusal": "No."}}]},
            "choices.0.message.content: Input should be a valid string",
        ),
        ("ollama", {"done": True}, "message: Field required"),
        ("ollama", openai_reply("{}"), "message: Field required"),
        ("copilot", ollama_reply("{}"), "choices: Field required"),
    ],
)
def test_reply_without_content_raises(
    provider: str, reply: dict[str, Any], problem: str
) -> None:
    server = FakeLLMServer(json=reply)
    client = MAKERS[provider](server.transport)

    message = str(call(client))

    assert message.startswith(
        f"{provider}: unexpected reply from {client.url} ({problem}"
    )


def echo_headers(status: int) -> httpx.MockTransport:
    """Return a server that answers with the request's Authorization header."""

    def handle(request: httpx.Request) -> httpx.Response:
        auth = request.headers["Authorization"]
        if status == 200:
            return httpx.Response(200, json={"headers": {"Authorization": auth}})
        return httpx.Response(status, text=f"bad credentials: {auth}")

    return httpx.MockTransport(handle)


@pytest.mark.parametrize("status", [401, 200])
@pytest.mark.parametrize("provider", ["copilot", "openai"])
def test_credentials_are_redacted_from_errors(provider: str, status: int) -> None:
    client = MAKERS[provider](echo_headers(status))

    error = call(client)
    message = str(error)
    trace = "".join(traceback.format_exception(error))

    assert TOKEN not in message
    assert TOKEN not in trace
    assert "input_value" not in trace
    assert "Bearer ***" in message
    assert TOKEN not in repr(client)


def test_token_from_gh_never_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)

    def gh(command: list[str], **kwargs: Any) -> Any:
        return llm.subprocess.CompletedProcess(command, 0, TOKEN + "\n", "")

    monkeypatch.setattr(llm.subprocess, "run", gh)
    server = FakeLLMServer(json=openai_reply('{"clips": []}'))

    CopilotClient("gpt-4.1", transport=server.transport).complete_json("s", "u")
    error = call(CopilotClient("gpt-4.1", transport=echo_headers(403)))

    assert server.request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert "copilot gpt-4.1 replied in" in caplog.text
    assert TOKEN not in caplog.text
    assert TOKEN not in str(error)
