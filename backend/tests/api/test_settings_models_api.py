"""POST /settings/models lists each provider's models for the model picker, and
PUT /settings?verify_llm=true tries a changed model before saving it. The
replies have the shapes recorded from the real services."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from clipforge import config
from clipforge.api.app import create_app
from clipforge.llm_responses import clear_model_cache
from fastapi.testclient import TestClient

TOKEN = "ghu_secret_token_123"
KEY = "sk-secret-key-123"
CHAT_OK = {"choices": [{"message": {"content": '{"ok": true}'}}]}
COPILOT_MODELS = {
    "object": "list",
    "data": [
        {
            "id": "claude-sonnet-5.5",
            "model_picker_enabled": True,
            "capabilities": {"type": "chat"},
            "supported_endpoints": ["/v1/messages", "/chat/completions"],
        },
        {
            "id": "gpt-6-luna",
            "model_picker_enabled": True,
            "capabilities": {"type": "chat"},
            "supported_endpoints": ["/responses", "ws:/responses"],
        },
        {
            "id": "gpt-4.1",
            "model_picker_enabled": False,
            "capabilities": {"type": "chat"},
        },
        {
            "id": "text-embedding-3-small",
            "model_picker_enabled": False,
            "capabilities": {"type": "embeddings"},
        },
    ],
}
OPENAI_MODELS = {
    "object": "list",
    "data": [{"id": "gpt-5", "object": "model"}, {"id": "gpt-5-mini"}],
}
OLLAMA_TAGS = {
    "models": [
        {"name": "llama3.2:latest", "model": "llama3.2:latest", "size": 2019393189},
        {"name": "qwen3:8b", "model": "qwen3:8b"},
    ]
}
MODEL_NOT_SUPPORTED = (
    '{"error":{"message":"The requested model is not supported.",'
    '"code":"model_not_supported","param":"model","type":"invalid_request_error"}}'
)


@pytest.fixture
def calls() -> list[httpx.Request]:
    return []


@pytest.fixture
def client(
    data_dir: Path, work_in_tmp: Path, calls: list[httpx.Request]
) -> Iterator[TestClient]:
    """An app whose LLM requests go to fake Copilot, OpenAI-compatible and
    Ollama servers; a chat request for a model other than a listed one gets
    Copilot's model_not_supported 400, a request with a wrong token a 401."""
    clear_model_cache()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        path = request.url.path
        auth = request.headers.get("authorization", "")
        if request.url.host == "api.githubcopilot.com":
            if auth != f"Bearer {TOKEN}":
                return httpx.Response(401, text=f"bad credentials {auth}")
            if path == "/models":
                return httpx.Response(200, json=COPILOT_MODELS)
            model = request.content.decode()
            if '"soclaude-sonnet-5-5"' in model:
                return httpx.Response(400, text=MODEL_NOT_SUPPORTED)
            return httpx.Response(200, json=CHAT_OK)
        if path == "/api/tags":
            return httpx.Response(200, json=OLLAMA_TAGS)
        if path == "/v1/models":
            return httpx.Response(200, json=OPENAI_MODELS)
        return httpx.Response(200, json=CHAT_OK)

    app = create_app(
        run_worker=False,
        caption_previews=False,
        llm_transport=httpx.MockTransport(handler),
    )
    with TestClient(app) as test_client:
        yield test_client


def models(client: TestClient, body: dict[str, Any]) -> dict[str, Any]:
    response = client.post("/api/settings/models", json=body)
    assert response.status_code == 200
    result: dict[str, Any] = response.json()
    return result


def test_copilot_lists_the_chat_models_of_the_account(
    client: TestClient, calls: list[httpx.Request]
) -> None:
    body = models(client, {"llm_provider": "copilot", "github_copilot_token": TOKEN})

    assert body == {
        "models": ["claude-sonnet-5.5", "gpt-6-luna", "gpt-4.1"],
        "error": None,
    }
    assert str(calls[0].url) == "https://api.githubcopilot.com/models"


def test_a_refused_copilot_token_lists_nothing_and_is_hidden(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/settings/models",
        json={"llm_provider": "copilot", "github_copilot_token": "ghu_wrong"},
    )

    body = response.json()
    assert body["models"] == []
    assert "HTTP 401" in body["error"] and "ghu_wrong" not in response.text


def test_openai_compatible_lists_the_models_of_the_base_url(
    client: TestClient, calls: list[httpx.Request]
) -> None:
    body = models(
        client,
        {
            "llm_provider": "openai",
            "openai_base_url": "https://llm.example/v1",
            "openai_api_key": KEY,
        },
    )

    assert body["models"] == ["gpt-5", "gpt-5-mini"]
    assert str(calls[0].url) == "https://llm.example/v1/models"
    assert calls[0].headers["authorization"] == f"Bearer {KEY}"


def test_ollama_lists_the_pulled_models(
    client: TestClient, calls: list[httpx.Request]
) -> None:
    body = models(
        client,
        {"llm_provider": "ollama", "ollama_host": "http://127.0.0.1:11434"},
    )

    assert body["models"] == ["llama3.2:latest", "qwen3:8b"]
    assert str(calls[0].url) == "http://127.0.0.1:11434/api/tags"


def test_claude_code_has_no_list(
    client: TestClient, calls: list[httpx.Request]
) -> None:
    body = models(client, {"llm_provider": "claude_code"})

    assert body == {"models": [], "error": None}
    assert calls == []


def put(client: TestClient, body: dict[str, Any]) -> httpx.Response:
    return client.put("/api/settings?verify_llm=true", json=body)


def test_a_model_that_answers_is_saved(
    client: TestClient, work_in_tmp: Path, calls: list[httpx.Request]
) -> None:
    response = put(
        client, {"github_copilot_token": TOKEN, "llm_model": "claude-sonnet-5.5"}
    )

    assert response.status_code == 200
    assert response.json()["llm_model"] == "claude-sonnet-5.5"
    assert config.settings.llm_model == "claude-sonnet-5.5"
    assert [r.url.path for r in calls if r.method == "POST"] == ["/chat/completions"]


def test_a_model_that_is_refused_is_not_saved_and_shows_the_providers_error(
    client: TestClient, work_in_tmp: Path
) -> None:
    put(client, {"github_copilot_token": TOKEN})
    before = config.settings.llm_model

    response = put(client, {"llm_model": "soclaude-sonnet-5-5"})

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "llm_rejected"
    assert "model_not_supported" in body["message"]
    assert "soclaude-sonnet-5-5" in body["message"]
    assert "nothing was saved" in body["message"]
    assert config.settings.llm_model == before
    assert client.get("/api/settings").json()["llm_model"] == before
    assert "soclaude" not in (work_in_tmp / ".env.local").read_text()


def test_a_refused_token_is_not_saved_and_never_shown(client: TestClient) -> None:
    response = put(client, {"github_copilot_token": "ghu_wrong"})

    assert response.status_code == 422
    assert "HTTP 401" in response.json()["message"]
    assert "ghu_wrong" not in response.text
    assert config.settings.github_copilot_token == ""


def test_settings_that_leave_the_model_alone_are_saved_without_a_call(
    client: TestClient, calls: list[httpx.Request]
) -> None:
    response = put(client, {"whisper_model": "medium"})

    assert response.status_code == 200
    assert calls == []


def test_without_verify_llm_the_model_is_saved_untried(
    client: TestClient, calls: list[httpx.Request]
) -> None:
    response = client.put("/api/settings", json={"llm_model": "anything"})

    assert response.status_code == 200
    assert calls == []
