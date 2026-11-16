"""Copilot's Responses API (STEERING 2026-10-31): models Copilot serves only
at /responses (per GET /models) are asked there, the others at
/chat/completions; the model list is fetched once. Recorded reply shapes in
tests/fakes.py; nothing touches the network except the opt-in live test.
"""

import json
import logging
from typing import Any

import httpx
import pytest
from clipforge.asset_rows import UsageRecordRow
from clipforge.config import Settings
from clipforge.llm import (
    CopilotClient,
    LLMError,
    create_client,
    gh_auth_token,
    reply_json,
)
from clipforge.llm_responses import ResponsesReply
from clipforge.usage import LLM_TOKENS, recording
from fakes import FakeLLMServer, openai_reply, responses_reply
from sqlalchemy import Engine
from sqlmodel import Session, select

SYSTEM = "You find clips in a transcript. Answer with JSON only."
USER = '[00:01.0-00:04.2] S0: Hello there.\nReturn {"clips": [...]}.'
REPLY = '{"clips": []}'
BASE = "https://api.githubcopilot.com"
# As GET /models lists them on the owner's account (2026-10-31).
MODELS: list[dict[str, Any]] = [
    {"id": "gpt-4.1", "policy": {"state": "enabled"}},
    {
        "id": "gpt-6-luna",
        "policy": {"state": "enabled"},
        "supported_endpoints": ["/responses", "ws:/responses"],
    },
    {
        "id": "gpt-5.4-nano",
        "supported_endpoints": ["/chat/completions", "/responses"],
    },
]


def copilot(server: FakeLLMServer, model: str, token: str = "tok") -> CopilotClient:
    return CopilotClient(model, token, transport=server.transport)


def test_a_responses_only_model_is_asked_at_responses() -> None:
    server = FakeLLMServer(json=responses_reply(REPLY), models=MODELS)

    assert copilot(server, "gpt-6-luna").complete_json(SYSTEM, USER) == REPLY

    request = server.request
    assert (request.method, str(request.url)) == ("POST", f"{BASE}/responses")
    assert json.loads(request.content) == {
        "model": "gpt-6-luna",
        "input": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        "text": {"format": {"type": "json_object"}},
    }
    assert request.headers["Authorization"] == "Bearer tok"
    assert request.headers["Copilot-Integration-Id"] == "vscode-chat"
    (listing,) = server.model_requests
    assert str(listing.url) == f"{BASE}/models"
    assert listing.headers["Authorization"] == "Bearer tok"


@pytest.mark.parametrize("model", ["gpt-4.1", "gpt-5.4-nano", "unlisted-model"])
def test_other_models_are_asked_at_chat_completions(model: str) -> None:
    server = FakeLLMServer(json=openai_reply(REPLY), models=MODELS)

    assert copilot(server, model).complete_json(SYSTEM, USER) == REPLY

    assert str(server.request.url) == f"{BASE}/chat/completions"
    assert json.loads(server.request.content)["model"] == model


def test_the_model_list_is_fetched_once_per_token() -> None:
    server = FakeLLMServer(json=responses_reply(REPLY), models=MODELS)
    client = copilot(server, "gpt-6-luna")

    client.complete_json(SYSTEM, USER)
    client.complete_json(SYSTEM, USER)
    copilot(server, "gpt-6-luna").complete_json(SYSTEM, USER)
    copilot(server, "gpt-6-luna", token="other").complete_json(SYSTEM, USER)

    assert len(server.requests) == 4
    tokens = [r.headers["Authorization"] for r in server.model_requests]
    assert tokens == ["Bearer tok", "Bearer other"]


def test_a_failed_model_list_falls_back_to_chat_and_is_retried(
    caplog: pytest.LogCaptureFixture,
) -> None:
    answers = iter([httpx.Response(500, text="down"), httpx.Response(200, json={})])
    asked: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        asked.append(f"{request.method} {request.url.path}")
        if request.url.path == "/models":
            return next(answers)
        return httpx.Response(200, json=openai_reply(REPLY))

    client = CopilotClient("gpt-6-luna", "tok", transport=httpx.MockTransport(handle))

    assert client.complete_json(SYSTEM, USER) == REPLY
    assert client.complete_json(SYSTEM, USER) == REPLY

    assert asked == [
        "GET /models",
        "POST /chat/completions",
        "GET /models",
        "POST /chat/completions",
    ]
    assert "copilot: HTTP 500 from https://api.githubcopilot.com/models" in caplog.text
    assert "using chat completions" in caplog.text


def test_the_responses_tokens_are_recorded(engine: Engine) -> None:
    server = FakeLLMServer(json=responses_reply("{}", total_tokens=51), models=MODELS)

    with recording(engine, None):
        copilot(server, "gpt-6-luna").complete_json("s", "u")

    with Session(engine) as session:
        rows = session.exec(select(UsageRecordRow)).all()
    assert [(r.kind, r.units) for r in rows] == [(LLM_TOKENS, 51)]


def test_the_texts_of_the_message_are_joined() -> None:
    reply = responses_reply('{"clips": ')
    reply["output"][1]["content"].append({"type": "output_text", "text": "[]}"})

    assert ResponsesReply.model_validate(reply).text() == REPLY


@pytest.mark.parametrize(
    ("status", "output"),
    [
        ("incomplete", []),
        ("completed", [{"type": "reasoning", "summary": []}]),
        ("completed", [{"type": "message", "content": [{"type": "refusal"}]}]),
    ],
)
def test_a_response_without_output_text_is_an_error(
    status: str, output: list[dict[str, Any]]
) -> None:
    server = FakeLLMServer(json={"status": status, "output": output}, models=MODELS)

    with pytest.raises(LLMError, match=f"no output text \\(status {status}\\)"):
        copilot(server, "gpt-6-luna").complete_json(SYSTEM, USER)


def test_an_http_error_at_responses_is_an_llm_error() -> None:
    server = FakeLLMServer(
        400, json={"error": {"code": "model_not_supported"}}, models=MODELS
    )

    with pytest.raises(LLMError, match="HTTP 400 from .*/responses") as caught:
        copilot(server, "gpt-6-luna").complete_json(SYSTEM, USER)

    assert caught.value.status_code == 400
    assert "model_not_supported" in str(caught.value)


@pytest.mark.live
def test_copilot_live_gpt_6_luna(caplog: pytest.LogCaptureFixture) -> None:
    """Opt-in (`pytest -m live`): Copilot's gpt-6-luna, a responses-only
    model, returns valid JSON."""
    caplog.set_level(logging.DEBUG)
    cfg = Settings(llm_provider="copilot", llm_model="gpt-6-luna")

    reply = create_client(cfg).complete_json(
        "You are a calculator. Answer with one JSON object only.",
        'What is 2 + 2? Answer as {"answer": <number>}.',
    )

    assert json.loads(reply_json(reply)) == {"answer": 4}
    assert "POST https://api.githubcopilot.com/responses" in caplog.text
    leaked = (
        cfg.github_copilot_token or gh_auth_token(cfg.copilot_account)
    ) in caplog.text
    assert not leaked, "the Copilot token was logged"
