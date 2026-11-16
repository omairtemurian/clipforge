"""Test doubles for the LLM (tests only; never imported by clipforge, SPEC 2).

FakeLLMClient replaces the whole LLMClient: it replays canned replies, such
as fixtures/llm_response.json, and records the prompts it was given.
FakeLLMServer replaces only the LLM's HTTP server, so the real clients in
clipforge.llm can be tested through an httpx.MockTransport.
"""

from collections import deque
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LLM_RESPONSE = FIXTURES / "llm_response.json"


class FakeLLMClient:
    """An LLMClient that returns canned replies in order and records prompts.

    A str reply is returned as it is; a Path reply is the text of that file,
    read when the reply is due. With no replies, every call returns
    fixtures/llm_response.json. After the last reply, repeat_last returns it
    again; otherwise one more call fails the test with AssertionError.
    """

    def __init__(self, *replies: str | Path, repeat_last: bool = False) -> None:
        if not replies:
            replies, repeat_last = (LLM_RESPONSE,), True
        self._replies: deque[str | Path] = deque(replies)
        self.repeat_last = repeat_last
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> str:
        """Record the prompt and return the next canned reply."""
        self.calls.append((system, user))
        if not self._replies:
            raise AssertionError(
                f"FakeLLMClient has no reply left for call {len(self.calls)}"
            )
        if self.repeat_last and len(self._replies) == 1:
            reply = self._replies[0]
        else:
            reply = self._replies.popleft()
        return reply.read_text(encoding="utf-8") if isinstance(reply, Path) else reply


def openai_reply(
    content: str, *, tokens: tuple[int, int] | None = None
) -> dict[str, Any]:
    """Return an OpenAI chat completion (as Copilot sends it) with content;
    tokens, if given, is the (prompt, completion) tokens of its `usage`."""
    reply: dict[str, Any] = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "gpt-4.1-2025-04-14",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    if tokens is not None:
        prompt, completion = tokens
        reply["usage"] = {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
        }
    return reply


def responses_reply(text: str, *, total_tokens: int | None = None) -> dict[str, Any]:
    """Return a Responses API answer (as Copilot sends it, trimmed from a
    recorded gpt-5.4-nano reply) whose message says text, after a reasoning
    item; total_tokens, if given, is its usage.total_tokens."""
    reply: dict[str, Any] = {
        "id": "resp-test",
        "object": "response",
        "model": "gpt-6-luna",
        "status": "completed",
        "output": [
            {"id": "rs-test", "type": "reasoning", "summary": []},
            {
                "id": "msg-test",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "phase": "final_answer",
                "content": [
                    {
                        "type": "output_text",
                        "text": text,
                        "annotations": [],
                        "logprobs": [],
                    }
                ],
            },
        ],
        "text": {"format": {"type": "json_object"}, "verbosity": "medium"},
        "copilot_usage": {"token_details": [], "total_nano_aiu": 0},
    }
    if total_tokens is not None:
        reply["usage"] = {
            "input_tokens": total_tokens - 12,
            "output_tokens": 12,
            "total_tokens": total_tokens,
        }
    return reply


def ollama_reply(
    content: str, *, tokens: tuple[int, int] | None = None
) -> dict[str, Any]:
    """Return an Ollama /api/chat answer (stream false) with content; tokens,
    if given, is its (prompt_eval_count, eval_count)."""
    reply: dict[str, Any] = {
        "model": "llama3.2",
        "created_at": "2026-10-31T00:00:00Z",
        "message": {"role": "assistant", "content": content},
        "done": True,
    }
    if tokens is not None:
        reply["prompt_eval_count"], reply["eval_count"] = tokens
    return reply


def anthropic_reply(
    content: str, *, tokens: tuple[int, int] = (21, 305)
) -> dict[str, Any]:
    """Return an Anthropic Messages API answer (the shape of the example in
    platform.claude.com/docs/en/get-started, 2026-10-31) with content as its
    one text block; tokens is its (input_tokens, output_tokens)."""
    return {
        "model": "claude-sonnet-5-5",
        "id": "msg_013mHbppMPd2PrVJzGMZPt2D",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": content}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "stop_details": None,
        "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
    }


class FakeLLMServer:
    """A fake LLM HTTP server: pass .transport to a client in clipforge.llm.

    It records every request in .requests and answers each one with status
    and a JSON body (json) or a text body (text). Copilot's model list
    (GET .../models) is apart: those requests go to .model_requests and get
    {"data": models} (no model by default, so the client uses chat
    completions).
    """

    def __init__(
        self,
        status: int = 200,
        *,
        json: Any = None,
        text: str | None = None,
        models: list[dict[str, Any]] | None = None,
    ) -> None:
        self.status = status
        self.json = json
        self.text = text
        self.models = models or []
        self.requests: list[httpx.Request] = []
        self.model_requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    @property
    def request(self) -> httpx.Request:
        """Return the only request received (fails the test otherwise)."""
        assert len(self.requests) == 1, f"{len(self.requests)} requests, not 1"
        return self.requests[0]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/models"):
            self.model_requests.append(request)
            return httpx.Response(200, json={"data": self.models, "object": "list"})
        self.requests.append(request)
        if self.text is not None:
            return httpx.Response(self.status, text=self.text)
        return httpx.Response(self.status, json=self.json)
