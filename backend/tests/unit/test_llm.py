"""LLM clients (SPEC 2, SPEC 13.1): the exact requests they send, through a
fake HTTP server, and how the Copilot token is found.
"""

import json
import logging
import subprocess
from typing import Any

import clipforge
import httpx
import pytest
from clipforge import config, llm
from clipforge.config import Settings
from clipforge.llm import (
    CopilotClient,
    LLMClient,
    LLMError,
    OllamaClient,
    OpenAICompatClient,
    create_client,
    gh_auth_token,
    reply_json,
)
from clipforge.llm_http import join_url
from fakes import FakeLLMServer, ollama_reply, openai_reply

SYSTEM = "You find clips in a transcript. Answer with JSON only."
USER = '[00:01.0-00:04.2] S0: Hello there.\nReturn {"clips": [...]}.'
REPLY = '{"clips": []}'
MESSAGES = [
    {"role": "system", "content": SYSTEM},
    {"role": "user", "content": USER},
]
GH_COMMAND = ["gh", "auth", "token", "-h", "github.com"]
GITHUB_MODELS = "https://models.github.ai/inference/chat/completions"


class FakeGh:
    """Stands in for subprocess.run: answers `gh auth token`, records calls."""

    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(
        self, command: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append((command, kwargs))
        return subprocess.CompletedProcess(
            command, self.returncode, self.stdout, self.stderr
        )


def body(request: httpx.Request) -> Any:
    """Return the parsed JSON body of request."""
    return json.loads(request.content)


def no_gh(*args: Any, **kwargs: Any) -> Any:
    raise AssertionError("gh must not run when a token is configured")


def test_copilot_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm.subprocess, "run", no_gh)
    server = FakeLLMServer(json=openai_reply(REPLY))
    client = CopilotClient("gpt-4.1", "test-token", transport=server.transport)

    assert client.complete_json(SYSTEM, USER) == REPLY

    request = server.request
    assert request.method == "POST"
    assert str(request.url) == "https://api.githubcopilot.com/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-token"
    assert request.headers["Copilot-Integration-Id"] == "vscode-chat"
    assert request.headers["Editor-Version"] == "clipforge/0.1.0"
    assert clipforge.__version__ == "0.1.0"
    assert request.headers["Content-Type"] == "application/json"
    assert body(request) == {
        "model": "gpt-4.1",
        "messages": MESSAGES,
        "response_format": {"type": "json_object"},
    }


def test_copilot_token_from_github_copilot_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm.subprocess, "run", no_gh)
    monkeypatch.setenv("GITHUB_COPILOT_TOKEN", "env-token")
    server = FakeLLMServer(json=openai_reply(REPLY))
    client = create_client(Settings(llm_provider="copilot"), transport=server.transport)

    client.complete_json(SYSTEM, USER)

    assert server.request.headers["Authorization"] == "Bearer env-token"


def test_copilot_token_from_gh_is_fetched_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGh(stdout="gho_from_gh\n")
    monkeypatch.setattr(llm.subprocess, "run", gh)
    server = FakeLLMServer(json=openai_reply(REPLY))
    cfg = Settings(llm_provider="copilot", github_copilot_token="")
    client = create_client(cfg, transport=server.transport)
    assert gh.calls == []

    client.complete_json(SYSTEM, USER)
    client.complete_json(SYSTEM, USER)

    assert [command for command, _ in gh.calls] == [GH_COMMAND]
    assert "shell" not in gh.calls[0][1]
    assert [r.headers["Authorization"] for r in server.requests] == [
        "Bearer gho_from_gh",
        "Bearer gho_from_gh",
    ]


def test_copilot_token_is_the_copilot_account_s(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh = FakeGh(stdout="gho_other\n")
    monkeypatch.setattr(llm.subprocess, "run", gh)
    monkeypatch.setenv("COPILOT_ACCOUNT", "someone-else")
    server = FakeLLMServer(json=openai_reply(REPLY))
    cfg = Settings(llm_provider="copilot", github_copilot_token="")

    create_client(cfg, transport=server.transport).complete_json(SYSTEM, USER)

    assert [command for command, _ in gh.calls] == [
        ["gh", "auth", "token", "-u", "someone-else", "-h", "github.com"]
    ]


@pytest.mark.parametrize(
    ("gh", "detail"),
    [
        (
            FakeGh(1, stderr="no oauth token found for github.com\n"),
            "no oauth token found for github.com",
        ),
        (FakeGh(0, stdout="\n"), "exit code 0"),
    ],
)
def test_gh_without_a_token_raises(
    monkeypatch: pytest.MonkeyPatch, gh: FakeGh, detail: str
) -> None:
    monkeypatch.setattr(llm.subprocess, "run", gh)
    server = FakeLLMServer(json=openai_reply(REPLY))
    client = CopilotClient("gpt-4.1", transport=server.transport)

    with pytest.raises(LLMError) as caught:
        client.complete_json(SYSTEM, USER)

    assert str(caught.value) == (
        f"copilot: no token: {detail}; set GITHUB_COPILOT_TOKEN or run "
        "`gh auth login -h github.com`"
    )
    assert server.requests == []


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (FileNotFoundError(2, "No such file or directory"), "cannot run gh"),
        (subprocess.TimeoutExpired(GH_COMMAND, 30), "took over 30s"),
    ],
)
def test_gh_that_cannot_run_raises(
    monkeypatch: pytest.MonkeyPatch, error: Exception, message: str
) -> None:
    def fail(*args: Any, **kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr(llm.subprocess, "run", fail)

    with pytest.raises(LLMError, match=message):
        gh_auth_token("octocat")


def test_openai_compat_request() -> None:
    server = FakeLLMServer(json=openai_reply(REPLY))
    client = OpenAICompatClient(
        "https://api.openai.com/v1",
        "sk-test",
        "gpt-4.1-mini",
        transport=server.transport,
    )

    assert client.complete_json(SYSTEM, USER) == REPLY

    request = server.request
    assert request.method == "POST"
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer sk-test"
    assert request.headers["Content-Type"] == "application/json"
    assert "Copilot-Integration-Id" not in request.headers
    assert body(request) == {
        "model": "gpt-4.1-mini",
        "messages": MESSAGES,
        "response_format": {"type": "json_object"},
    }


def test_openai_compat_without_a_key_sends_no_authorization() -> None:
    server = FakeLLMServer(json=openai_reply(REPLY))
    client = OpenAICompatClient(
        "http://127.0.0.1:1234/v1", "", "local-model", transport=server.transport
    )

    assert client.complete_json(SYSTEM, USER) == REPLY
    assert "Authorization" not in server.request.headers


@pytest.mark.parametrize(
    "base_url",
    ["https://models.github.ai/inference", "https://models.github.ai/inference/"],
)
def test_github_models_base_url(base_url: str) -> None:
    server = FakeLLMServer(json=openai_reply(REPLY))
    cfg = Settings(
        llm_provider="openai",
        openai_base_url=base_url,
        openai_api_key="github-pat",
        llm_model="openai/gpt-4.1",
    )

    reply = create_client(cfg, transport=server.transport).complete_json(SYSTEM, USER)

    assert reply == REPLY
    assert str(server.request.url) == GITHUB_MODELS
    assert server.request.headers["Authorization"] == "Bearer github-pat"
    assert body(server.request)["model"] == "openai/gpt-4.1"


@pytest.mark.parametrize(
    ("base", "path", "url"),
    [
        ("https://models.github.ai/inference", "chat/completions", GITHUB_MODELS),
        ("https://models.github.ai/inference/", "chat/completions", GITHUB_MODELS),
        ("https://models.github.ai/inference//", "/chat/completions", GITHUB_MODELS),
        ("http://localhost:11434", "api/chat", "http://localhost:11434/api/chat"),
        ("http://localhost:11434/", "/api/chat", "http://localhost:11434/api/chat"),
    ],
)
def test_join_url_has_one_slash(base: str, path: str, url: str) -> None:
    assert join_url(base, path) == url


def test_ollama_request() -> None:
    server = FakeLLMServer(json=ollama_reply(REPLY))
    client = OllamaClient(
        "http://localhost:11434", "llama3.2", transport=server.transport
    )

    assert client.complete_json(SYSTEM, USER) == REPLY

    request = server.request
    assert request.method == "POST"
    assert str(request.url) == "http://localhost:11434/api/chat"
    assert "Authorization" not in request.headers
    assert request.headers["Content-Type"] == "application/json"
    assert body(request) == {
        "model": "llama3.2",
        "messages": MESSAGES,
        "format": "json",
        "stream": False,
    }


@pytest.mark.parametrize(
    ("provider", "client_type", "url"),
    [
        ("copilot", CopilotClient, "https://api.githubcopilot.com/chat/completions"),
        ("openai", OpenAICompatClient, "https://api.openai.com/v1/chat/completions"),
        ("ollama", OllamaClient, "http://127.0.0.1:11434/api/chat"),
    ],
)
def test_create_client_follows_llm_provider(
    monkeypatch: pytest.MonkeyPatch, provider: str, client_type: type, url: str
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("LLM_MODEL", "model-x")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    monkeypatch.setattr(config, "settings", Settings())

    client = create_client()

    assert type(client) is client_type
    assert isinstance(client, LLMClient)
    assert (client.url, client.model) == (url, "model-x")


@pytest.mark.live
@pytest.mark.parametrize("model", ["claude-sonnet-5.5", "gpt-6-luna"])
def test_copilot_live_answers_with_json(
    caplog: pytest.LogCaptureFixture, model: str
) -> None:
    """Opt-in (`pytest -m live`): the default model (claude-sonnet-5.5, on
    /chat/completions) and its alternative (gpt-6-luna, on /responses) of
    the default account return valid JSON, maybe in a code fence."""
    caplog.set_level(logging.DEBUG)
    cfg = Settings(llm_provider="copilot", llm_model=model)

    reply = create_client(cfg).complete_json(
        "You are a calculator. Answer with one JSON object only.",
        'What is 2 + 2? Answer as {"answer": <number>}.',
    )

    assert json.loads(reply_json(reply)) == {"answer": 4}
    assert f"copilot {model} replied in" in caplog.text
    token = cfg.github_copilot_token or gh_auth_token(cfg.copilot_account)
    assert token not in caplog.text, "the Copilot token was logged"
