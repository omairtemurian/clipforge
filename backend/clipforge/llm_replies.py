"""The reply shapes of the chat APIs in clipforge.llm (an OpenAI chat
completion for Copilot and OpenAI-compatible servers, Ollama's /api/chat),
and reply_json, the JSON text of a model's reply."""

import re

from pydantic import BaseModel, Field

# A reply that is one Markdown code block: ``` and an optional language tag
# (Claude models wrap JSON in ```json even in JSON mode), the code, ```.
CODE_FENCE = re.compile(r"\s*```[\w+-]*[^\S\n]*\n?(.*?)\s*```\s*", re.DOTALL)


def reply_json(reply: str) -> str:
    """Return reply without the Markdown code fence around it, if any.

    Only a fence around the whole reply is removed; a reply with text before
    or after its code block is returned as it is, so that it fails JSON
    validation and the caller asks the model again.
    """
    block = CODE_FENCE.fullmatch(reply)
    return block[1] if block else reply


class _Message(BaseModel):
    content: str


class _Choice(BaseModel):
    message: _Message


class _TokenUsage(BaseModel):
    """The `usage` of an OpenAI chat completion."""

    total_tokens: int | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def total(self) -> int:
        """Return total_tokens, or the prompt and completion tokens if absent."""
        if self.total_tokens is not None:
            return self.total_tokens
        return self.prompt_tokens + self.completion_tokens


class ChatCompletion(BaseModel):
    """The part of an OpenAI chat completion that holds the reply and the
    tokens it cost (absent from some servers)."""

    choices: list[_Choice] = Field(min_length=1)
    usage: _TokenUsage | None = None


class OllamaChat(BaseModel):
    """The part of an Ollama /api/chat answer (stream false) with the reply
    and the tokens of the prompt and of the reply."""

    message: _Message
    prompt_eval_count: int = 0
    eval_count: int = 0
