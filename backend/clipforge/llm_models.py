"""The model lists of the LLM providers, for the Settings page's model picker.

Shapes (checked 2026-11-03):
- Copilot, GET https://api.githubcopilot.com/models: `data[]` with `id`,
  `model_picker_enabled` and `capabilities.type` ("chat" or "embeddings"),
  as recorded from a real account.
- OpenAI-compatible, GET {base}/models: `data[]` with `id`
  (https://developers.openai.com/api/reference/resources/models/methods/list).
- Ollama, GET {host}/api/tags: `models[]` with `name`
  (https://github.com/ollama/ollama/blob/main/docs/api.md#list-local-models).
- Anthropic, GET {base}/v1/models: see llm_anthropic.
"""

from pydantic import BaseModel

__all__ = [
    "CopilotModels",
    "OllamaTags",
    "OpenAIModels",
    "copilot_ids",
    "ollama_ids",
    "openai_ids",
]


class _Capabilities(BaseModel):
    type: str = "chat"


class _CopilotModel(BaseModel):
    id: str
    model_picker_enabled: bool = False
    capabilities: _Capabilities = _Capabilities()


class CopilotModels(BaseModel):
    """The answer of Copilot's GET /models."""

    data: list[_CopilotModel]


class _Id(BaseModel):
    id: str


class OpenAIModels(BaseModel):
    """The answer of an OpenAI-compatible GET /models."""

    data: list[_Id]


class _Tag(BaseModel):
    name: str


class OllamaTags(BaseModel):
    """The answer of Ollama's GET /api/tags."""

    models: list[_Tag]


def copilot_ids(models: CopilotModels) -> list[str]:
    """Return the ids of the chat models of the account, the ones that
    Copilot's own model picker shows first."""
    chat = [m for m in models.data if m.capabilities.type == "chat"]
    shown = [m.id for m in chat if m.model_picker_enabled]
    return shown + [m.id for m in chat if not m.model_picker_enabled]


def openai_ids(models: OpenAIModels) -> list[str]:
    """Return the model ids, in the server's order."""
    return [m.id for m in models.data]


def ollama_ids(tags: OllamaTags) -> list[str]:
    """Return the names of the models pulled on the Ollama server."""
    return [m.name for m in tags.models]
