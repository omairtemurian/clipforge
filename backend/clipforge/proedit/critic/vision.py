"""LLM requests with images for the Pro Edit critic (SPEC-v3 3.7, 1.6).

The clients of clipforge.llm send text only, so the critic builds its
requests here with the same endpoints, credentials and HTTP helper
(llm_http.post_json), one shape per provider (checked 2026-11-05):

- openai (OpenAI-compatible chat completions): the user message's content
  is a list of {"type": "text"} and {"type": "image_url", "image_url":
  {"url": "data:<media type>;base64,<data>"}} parts
  (https://developers.openai.com/api/docs/guides/images-vision).
- copilot: the same parts at /chat/completions with the header
  Copilot-Vision-Request: true, which Copilot needs to take images (sent by
  the Copilot clients that attach images, e.g. karthink/gptel and
  openclaw/openclaw); a model served only at /responses gets "input_text"
  and "input_image" parts there (same OpenAI guide).
- anthropic: "image" blocks with a base64 source before the text block
  (https://platform.claude.com/docs/en/build-with-claude/vision).
- ollama: the user message's "images" list of base64 strings
  (https://docs.ollama.com/api/chat).

Claude Code (and any other client) cannot send images: VisionUnsupported.
Each answer's tokens go to the usage meter as the text clients' do.
"""

import base64
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from clipforge import usage
from clipforge.llm import (
    COPILOT_BASE_URL,
    AnthropicClient,
    CopilotClient,
    LLMClient,
    OllamaClient,
    OpenAICompatClient,
)
from clipforge.llm_anthropic import MAX_TOKENS, AnthropicMessage
from clipforge.llm_http import join_url, post_json
from clipforge.llm_replies import ChatCompletion, OllamaChat
from clipforge.llm_responses import ResponsesReply

VISION_HEADER = "Copilot-Vision-Request"


class VisionUnsupported(Exception):
    """The client's provider has no way to send images."""


@dataclass(frozen=True)
class Image:
    """An encoded image (JPEG or PNG bytes) and its media type."""

    data: bytes
    media_type: str

    def base64(self) -> str:
        """Return the bytes as base64 text."""
        return base64.b64encode(self.data).decode("ascii")

    def data_url(self) -> str:
        """Return the image as a data: URL."""
        return f"data:{self.media_type};base64,{self.base64()}"


def can_send_images(llm: LLMClient) -> bool:
    """Whether llm's provider has an image request shape here."""
    return isinstance(llm, OpenAICompatClient | AnthropicClient | OllamaClient)


def model_key(llm: LLMClient) -> tuple[str, str, str]:
    """Return what identifies llm's model: provider, endpoint and model."""
    provider = str(getattr(llm, "provider", type(llm).__name__))
    return provider, str(getattr(llm, "url", "")), str(getattr(llm, "model", ""))


def complete_with_images(
    llm: LLMClient, system: str, user: str, images: Sequence[Image]
) -> str:
    """Return llm's reply text to the system prompt and the user message
    with images. Raises VisionUnsupported for a client that cannot send
    images and LLMError (llm_http) when the request fails."""
    if isinstance(llm, CopilotClient):
        return _copilot(llm, system, user, images)
    if isinstance(llm, OpenAICompatClient):
        return _openai(llm, system, user, images, extra_headers={})
    if isinstance(llm, AnthropicClient):
        return _anthropic(llm, system, user, images)
    if isinstance(llm, OllamaClient):
        return _ollama(llm, system, user, images)
    raise VisionUnsupported(
        f"the {model_key(llm)[0]} provider cannot send images to the model"
    )


def openai_parts(user: str, images: Sequence[Image]) -> list[dict[str, Any]]:
    """Return the chat completions content parts: the text, then each image."""
    return [
        {"type": "text", "text": user},
        *({"type": "image_url", "image_url": {"url": i.data_url()}} for i in images),
    ]


def _openai(
    llm: OpenAICompatClient,
    system: str,
    user: str,
    images: Sequence[Image],
    *,
    extra_headers: dict[str, str],
) -> str:
    key = llm._credential()
    body = {
        "model": llm.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": openai_parts(user, images)},
        ],
        "response_format": {"type": "json_object"},
    }
    reply = post_json(
        llm.provider,
        llm.url,
        body,
        ChatCompletion,
        headers=llm._headers(key) | extra_headers,
        secret=key,
        transport=llm._transport,
    )
    if reply.usage is not None:
        usage.record_tokens(reply.usage.total())
    return reply.choices[0].message.content


def _copilot(
    llm: CopilotClient, system: str, user: str, images: Sequence[Image]
) -> str:
    key = llm._credential()
    vision = {VISION_HEADER: "true"}
    if not llm._responses_only(key):
        return _openai(llm, system, user, images, extra_headers=vision)
    content = [
        {"type": "input_text", "text": user},
        *({"type": "input_image", "image_url": i.data_url()} for i in images),
    ]
    body = {
        "model": llm.model,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "text": {"format": {"type": "json_object"}},
    }
    reply = post_json(
        llm.provider,
        join_url(COPILOT_BASE_URL, "responses"),
        body,
        ResponsesReply,
        headers=llm._headers(key) | vision,
        secret=key,
        transport=llm._transport,
    )
    if reply.usage is not None:
        usage.record_tokens(reply.usage.total_tokens)
    return reply.text()


def _anthropic(
    llm: AnthropicClient, system: str, user: str, images: Sequence[Image]
) -> str:
    blocks: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.media_type,
                "data": image.base64(),
            },
        }
        for image in images
    ]
    body = {
        "model": llm.model,
        "max_tokens": MAX_TOKENS,
        "system": system,
        "messages": [
            {"role": "user", "content": [*blocks, {"type": "text", "text": user}]}
        ],
    }
    reply = post_json(
        llm.provider,
        llm.url,
        body,
        AnthropicMessage,
        headers=llm._headers(),
        secret=llm._api_key,
        transport=llm._transport,
    )
    if reply.usage is not None:
        usage.record_tokens(reply.usage.input_tokens + reply.usage.output_tokens)
    return reply.text()


def _ollama(llm: OllamaClient, system: str, user: str, images: Sequence[Image]) -> str:
    body = {
        "model": llm.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user, "images": [i.base64() for i in images]},
        ],
        "format": "json",
        "stream": False,
    }
    reply = post_json(
        llm.provider,
        llm.url,
        body,
        OllamaChat,
        headers={},
        secret="",
        transport=llm._transport,
    )
    usage.record_tokens(reply.prompt_eval_count + reply.eval_count)
    return reply.message.content
