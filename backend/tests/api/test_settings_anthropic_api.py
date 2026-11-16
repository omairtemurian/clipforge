"""Settings endpoints with LLM_PROVIDER=anthropic: the key and model are
saved like the others, the connection test asks Anthropic's API, and
POST /settings/models lists the key's models for the model field."""

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from clipforge import config
from clipforge.api.app import create_app
from fakes import anthropic_reply
from fastapi.testclient import TestClient

KEY = "sk-ant-secret-123"
MODELS = {
    "data": [
        {"type": "model", "id": "claude-opus-5-5"},
        {"type": "model", "id": "claude-sonnet-5-5"},
    ],
    "has_more": False,
    "first_id": "claude-opus-5-5",
    "last_id": "claude-sonnet-5-5",
}


@pytest.fixture
def calls() -> list[httpx.Request]:
    return []


@pytest.fixture
def client(
    data_dir: Path, work_in_tmp: Path, calls: list[httpx.Request]
) -> Iterator[TestClient]:
    """An app whose LLM requests go to a fake Anthropic API; a request with
    a key other than KEY gets a 401 that echoes it."""

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        key = request.headers.get("x-api-key", "")
        if key != KEY:
            return httpx.Response(401, text=f"invalid x-api-key {key}")
        if request.url.path == "/v1/models":
            return httpx.Response(200, json=MODELS)
        return httpx.Response(200, json=anthropic_reply('{"ok": true}'))

    app = create_app(
        run_worker=False,
        caption_previews=False,
        llm_transport=httpx.MockTransport(handler),
    )
    with TestClient(app) as test_client:
        yield test_client


def test_the_anthropic_settings_are_saved_and_the_key_never_shown(
    client: TestClient, work_in_tmp: Path
) -> None:
    body = client.put(
        "/api/settings",
        json={
            "llm_provider": "anthropic",
            "anthropic_api_key": KEY,
            "anthropic_model": "claude-opus-5-5",
        },
    ).json()

    assert body["llm_provider"] == "anthropic"
    assert body["anthropic_api_key_set"] is True
    assert body["anthropic_model"] == "claude-opus-5-5"
    assert body["anthropic_base_url"] == "https://api.anthropic.com"
    assert KEY not in json.dumps(body)
    assert config.settings.anthropic_api_key == KEY
    assert "ANTHROPIC_API_KEY=" in (work_in_tmp / ".env.local").read_text()


def test_test_llm_asks_anthropic_with_its_model(
    client: TestClient, calls: list[httpx.Request]
) -> None:
    response = client.post(
        "/api/settings/test-llm",
        json={"llm_provider": "anthropic", "anthropic_api_key": KEY},
    )

    assert response.json() == {
        "ok": True,
        "provider": "anthropic",
        "model": "claude-sonnet-5-5",
        "message": '{"ok": true}',
    }
    (request,) = calls
    assert str(request.url) == "https://api.anthropic.com/v1/messages"


def test_test_llm_without_a_key_explains_what_to_set(client: TestClient) -> None:
    body = client.post(
        "/api/settings/test-llm", json={"llm_provider": "anthropic"}
    ).json()

    assert body["ok"] is False
    assert "set ANTHROPIC_API_KEY" in body["message"]


def test_models_are_listed_with_the_key_in_the_body(
    client: TestClient, calls: list[httpx.Request]
) -> None:
    response = client.post(
        "/api/settings/models",
        json={"llm_provider": "anthropic", "anthropic_api_key": KEY},
    )

    assert response.json() == {
        "models": ["claude-opus-5-5", "claude-sonnet-5-5"],
        "error": None,
    }
    assert str(calls[0].url) == "https://api.anthropic.com/v1/models?limit=1000"


def test_a_refused_key_lists_no_models_and_hides_the_key(client: TestClient) -> None:
    wrong = "sk-ant-wrong-456"

    response = client.post(
        "/api/settings/models",
        json={"llm_provider": "anthropic", "anthropic_api_key": wrong},
    )

    body = response.json()
    assert body["models"] == []
    assert "HTTP 401" in body["error"] and "***" in body["error"]
    assert wrong not in response.text
