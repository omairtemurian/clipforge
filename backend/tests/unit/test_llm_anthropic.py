"""Tests for AnthropicClient (LLM_PROVIDER=anthropic): the request it builds,
the replies it reads (recorded shapes, no network), the model list, and
curate's retry with it. The live test is opt-in (`pytest -m live`) and needs
ANTHROPIC_API_KEY."""

import json
import os
from typing import Any

import httpx
import pytest
from clipforge import config, usage
from clipforge.asset_rows import UsageRecordRow
from clipforge.config import Settings
from clipforge.llm import (
    AnthropicClient,
    LLMClient,
    LLMError,
    create_client,
    model_of,
    reply_json,
)
from clipforge.llm_anthropic import ANTHROPIC_VERSION, MAX_TOKENS
from clipforge.models import CandidateList
from clipforge.pipeline.curate import Window, ask_window
from clipforge.pipeline.enrich import PromptLine
from fakes import LLM_RESPONSE, FakeLLMServer, anthropic_reply
from sqlalchemy import Engine
from sqlmodel import Session, select

KEY = "sk-ant-test-key"
SYSTEM = "You find clips in a transcript. Answer with JSON only."
USER = "[00:01.0-00:04.2] S0: Hello there."
CLIPS_JSON = LLM_RESPONSE.read_text(encoding="utf-8").strip()


def client(
    server: FakeLLMServer | httpx.MockTransport, key: str = KEY
) -> AnthropicClient:
    transport = server if isinstance(server, httpx.MockTransport) else server.transport
    return AnthropicClient(
        "https://api.anthropic.com", key, "claude-sonnet-5-5", transport=transport
    )


def test_request_has_the_documented_url_headers_and_body() -> None:
    server = FakeLLMServer(json=anthropic_reply('{"ok": true}'))

    assert client(server).complete_json(SYSTEM, USER) == '{"ok": true}'

    request = server.request
    assert request.method == "POST"
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == ANTHROPIC_VERSION == "2026-10-21"
    assert request.headers["content-type"] == "application/json"
    assert "authorization" not in request.headers
    assert json.loads(request.content) == {
        "model": "claude-sonnet-5-5",
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM,
        "messages": [{"role": "user", "content": USER}],
    }


def test_the_reply_is_the_text_blocks_joined() -> None:
    reply = anthropic_reply("")
    reply["content"] = [
        {"type": "thinking", "thinking": "hmm", "signature": "x"},
        {"type": "text", "text": '{"clips":'},
        {"type": "text", "text": " []}"},
    ]

    assert client(FakeLLMServer(json=reply)).complete_json(SYSTEM, USER) == (
        '{"clips": []}'
    )


def test_a_fenced_reply_reads_as_json_after_reply_json() -> None:
    server = FakeLLMServer(json=anthropic_reply('```json\n{"ok": true}\n```'))

    assert json.loads(reply_json(client(server).complete_json(SYSTEM, USER))) == {
        "ok": True
    }


def test_input_and_output_tokens_are_recorded(engine: Engine) -> None:
    server = FakeLLMServer(json=anthropic_reply("{}", tokens=(120, 30)))

    with usage.recording(engine, None):
        client(server).complete_json(SYSTEM, USER)

    with Session(engine) as session:
        (record,) = session.exec(select(UsageRecordRow)).all()
    assert (record.kind, record.units) == (usage.LLM_TOKENS, 150)


def test_no_key_raises_without_a_request() -> None:
    server = FakeLLMServer(json=anthropic_reply("{}"))

    with pytest.raises(LLMError, match="no API key: set ANTHROPIC_API_KEY"):
        client(server, key="").complete_json(SYSTEM, USER)

    assert server.requests == []


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (
            401,
            {"type": "error", "error": {"type": "authentication_error"}},
            "HTTP 401",
        ),
        (200, {"id": "msg_1", "type": "message"}, "unexpected reply"),
    ],
)
def test_a_failure_is_an_llm_error_without_the_key(
    status: int, body: dict[str, Any], error: str
) -> None:
    body["echo"] = KEY
    server = FakeLLMServer(status, json=body)

    with pytest.raises(LLMError, match=error) as caught:
        client(server).complete_json(SYSTEM, USER)

    assert KEY not in str(caught.value)


def test_list_models_reads_the_ids_newest_first() -> None:
    server = FakeLLMServer(
        models=[
            {
                "type": "model",
                "id": "claude-opus-5-5",
                "display_name": "Claude Opus 5.5",
            },
            {
                "type": "model",
                "id": "claude-sonnet-5-5",
                "display_name": "Claude Sonnet 5.5",
            },
        ]
    )

    assert client(server).list_models() == ["claude-opus-5-5", "claude-sonnet-5-5"]

    (request,) = server.model_requests
    assert str(request.url) == "https://api.anthropic.com/v1/models?limit=1000"
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == ANTHROPIC_VERSION


def test_create_client_uses_the_anthropic_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config, "settings", Settings())
    cfg = Settings(
        llm_provider="anthropic",
        llm_model="ignored",
        anthropic_api_key=KEY,
        anthropic_base_url="https://proxy.example/anthropic",
        anthropic_model="claude-opus-5-5",
    )

    made = create_client(cfg)

    assert isinstance(made, AnthropicClient) and isinstance(made, LLMClient)
    assert made.url == "https://proxy.example/anthropic/v1/messages"
    assert made.model == model_of(cfg) == "claude-opus-5-5"


def test_curate_retries_an_invalid_anthropic_reply() -> None:
    replies = [
        f"Here are the clips:\n```json\n{CLIPS_JSON}\n```",
        f"```json\n{CLIPS_JSON}\n```",
    ]
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=anthropic_reply(replies[len(sent) - 1]))

    window = Window(0, 600, [PromptLine(0.5, "[00:00.5-00:01.4] S0: Hi everyone.")])

    clips = ask_window(client(httpx.MockTransport(answer)), "system", window)

    assert clips == CandidateList.model_validate_json(CLIPS_JSON).clips
    assert len(sent) == 2
    retry = json.loads(sent[1].content)["messages"][0]["content"]
    assert "Your previous reply for this transcript was not valid" in retry


@pytest.mark.live
def test_anthropic_live_answers_with_json() -> None:
    """Opt-in (`pytest -m live`, with ANTHROPIC_API_KEY): the default model
    returns valid JSON."""
    if (
        not os.environ.get("ANTHROPIC_API_KEY")
        and not config.settings.anthropic_api_key
    ):
        pytest.skip("no ANTHROPIC_API_KEY")
    cfg = Settings(llm_provider="anthropic")

    reply = create_client(cfg).complete_json(
        "You are a calculator. Answer with one JSON object only.",
        'What is 2 + 2? Answer as {"answer": <number>}.',
    )

    assert json.loads(reply_json(reply)) == {"answer": 4}
