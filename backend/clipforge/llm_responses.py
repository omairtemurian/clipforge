"""Copilot's Responses API (POST /responses) for the models it serves only
there, and the model list (GET /models) that tells which ones those are.

Some Copilot models (gpt-6-luna, gpt-5.6-luna) list `supported_endpoints`
["/responses", "ws:/responses"] and refuse /chat/completions with
`model_not_supported`; models without the field (gpt-4.1) use chat
completions. Each account's model list is fetched once per process and kept.

The request sends the system and user messages as `input` messages with
`text.format` json_object: Copilot refuses JSON mode unless an *input*
message says "json" (the `instructions` field does not count).
Shapes: https://developers.openai.com/api/reference/resources/responses/
methods/create (checked 2026-10-31) and a recorded Copilot reply.
"""

import hashlib
import logging
import threading
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from clipforge.llm_http import LLMError

logger = logging.getLogger(__name__)

RESPONSES = "/responses"
CHAT_COMPLETIONS = "/chat/completions"

# (model list URL, sha256 of the token) -> {model id: its supported_endpoints}
_endpoints: dict[tuple[str, str], dict[str, list[str] | None]] = {}
_lock = threading.Lock()


class _ModelInfo(BaseModel):
    """One model of GET /models; supported_endpoints is absent for most."""

    id: str
    supported_endpoints: list[str] | None = None


class ModelList(BaseModel):
    """The answer of Copilot's GET /models."""

    data: list[_ModelInfo]


class _OutputContent(BaseModel):
    type: str
    text: str = ""


class _OutputItem(BaseModel):
    """An item of a response's output: a message, a reasoning item, ..."""

    type: str
    content: list[_OutputContent] | None = None


class _ResponsesUsage(BaseModel):
    total_tokens: int = 0


class ResponsesReply(BaseModel):
    """The part of a Responses API answer with the reply and its tokens."""

    status: str | None = None
    output: list[_OutputItem]
    usage: _ResponsesUsage | None = None

    def text(self) -> str:
        """Return the text of the output_text parts of its messages.

        Raises LLMError if there is none (for example, an incomplete reply).
        """
        parts = [
            part.text
            for item in self.output
            if item.type == "message"
            for part in item.content or []
            if part.type == "output_text"
        ]
        if not parts:
            raise LLMError(
                f"copilot: the response has no output text (status {self.status})"
            )
        return "".join(parts)


def responses_body(model: str, messages: list[dict[str, str]]) -> dict[str, Any]:
    """Return the POST /responses body that asks model for JSON."""
    return {
        "model": model,
        "input": messages,
        "text": {"format": {"type": "json_object"}},
    }


def model_endpoints(
    models_url: str, token: str, fetch: Callable[[], ModelList]
) -> dict[str, list[str] | None]:
    """Return each model's supported_endpoints for the account of token.

    fetch() asks the server; it runs once per models_url and token, then the
    answer is kept for the life of the process. A failed fetch is not kept.
    """
    key = (models_url, hashlib.sha256(token.encode()).hexdigest())
    with _lock:
        known = _endpoints.get(key)
    if known is not None:
        return known
    models = {model.id: model.supported_endpoints for model in fetch().data}
    with _lock:
        _endpoints[key] = models
    return models


def clear_model_cache() -> None:
    """Forget every model list fetched so far (tests)."""
    with _lock:
        _endpoints.clear()


def responses_only(endpoints: dict[str, list[str] | None], model: str) -> bool:
    """Whether model is served at /responses but not at /chat/completions."""
    listed = endpoints.get(model) or []
    return RESPONSES in listed and CHAT_COMPLETIONS not in listed
