"""The Anthropic API client of clipforge.llm (LLM_PROVIDER=anthropic).

Request and reply shapes as Anthropic's API reference documents them
(https://platform.claude.com/docs/en/api/messages, /api/versioning and
/api/models/list, read 2026-10-31): POST {base}/v1/messages with headers
x-api-key and anthropic-version, body model, max_tokens, system and
messages; the reply's text is in content[] blocks of type "text" and its
tokens in usage.input_tokens and usage.output_tokens. GET {base}/v1/models
lists the models the key can use. The API has no JSON mode: the prompts ask
for JSON and the caller strips a code fence (reply_json).
"""

import httpx
from pydantic import BaseModel

from clipforge import usage
from clipforge.llm_http import LLMError, get_json, join_url, post_json

__all__ = [
    "ANTHROPIC_VERSION",
    "MAX_TOKENS",
    "AnthropicClient",
    "AnthropicMessage",
]

# The latest API version on 2026-10-31 (it removed temperature/top_p/top_k,
# which ClipForge does not send).
ANTHROPIC_VERSION = "2026-10-21"
# The longest reply asked for: a window's clip list is a few thousand tokens.
MAX_TOKENS = 8192
# GET /v1/models returns 20 models a page by default; 1000 is the largest page.
MODELS_PAGE = 1000


class _Block(BaseModel):
    type: str
    text: str = ""


class _Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class AnthropicMessage(BaseModel):
    """The part of a Messages API answer with the reply and its tokens."""

    content: list[_Block]
    usage: _Usage | None = None

    def text(self) -> str:
        """Return the text of the reply's text blocks, joined."""
        return "".join(block.text for block in self.content if block.type == "text")


class _ModelInfo(BaseModel):
    id: str


class _ModelList(BaseModel):
    data: list[_ModelInfo]


class AnthropicClient:
    """Anthropic's Messages API, with an API key (ANTHROPIC_API_KEY)."""

    provider = "anthropic"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = join_url(base_url, "v1/messages")
        self.models_url = join_url(base_url, "v1/models")
        self.model = model
        self._api_key = api_key
        self._transport = transport

    def complete_json(self, system: str, user: str) -> str:
        """Return the model's reply text to the system prompt and user message;
        record its input and output tokens in the usage meter."""
        body = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        reply = post_json(
            self.provider,
            self.url,
            body,
            AnthropicMessage,
            headers=self._headers(),
            secret=self._api_key,
            transport=self._transport,
        )
        if reply.usage is not None:
            usage.record_tokens(reply.usage.input_tokens + reply.usage.output_tokens)
        return reply.text()

    def list_models(self) -> list[str]:
        """Return the ids of the models the key can use, newest first."""
        models = get_json(
            self.provider,
            f"{self.models_url}?limit={MODELS_PAGE}",
            _ModelList,
            headers=self._headers(),
            secret=self._api_key,
            transport=self._transport,
        )
        return [model.id for model in models.data]

    def _headers(self) -> dict[str, str]:
        """Return the API key and version headers; raise LLMError without a key."""
        if not self._api_key:
            raise LLMError(
                "anthropic: no API key: set ANTHROPIC_API_KEY (Settings, Anthropic API)"
            )
        return {"x-api-key": self._api_key, "anthropic-version": ANTHROPIC_VERSION}
