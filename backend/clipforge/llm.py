"""LLM clients: ask a chat model for a JSON answer (SPEC 2, SPEC 13.1).

Every client has complete_json(system, user): it sends a system and a user
message and returns the model's reply text. The reply should be JSON but is
neither parsed nor checked here; the caller validates reply_json(reply), the
reply without a surrounding Markdown code fence (curate sends the validation
errors back to the model). create_client() returns the client
that LLM_PROVIDER names:

- copilot (default): GitHub Copilot's chat API, with GITHUB_COPILOT_TOKEN
  or the token of GitHub CLI account COPILOT_ACCOUNT;
  models Copilot serves only at /responses use that API (llm_responses).
- openai: any OpenAI-compatible API at OPENAI_BASE_URL, in JSON mode.
- ollama: an Ollama server at OLLAMA_HOST, with format=json.
- anthropic: Anthropic's Messages API with ANTHROPIC_API_KEY and
  ANTHROPIC_MODEL (llm_anthropic).
- claude_code: the Claude subscription through the Claude Code CLI
  (CLAUDE_CODE_BIN, CLAUDE_CODE_MODEL; llm_claude_code).

Each answer's token count (the `usage` of an OpenAI-style answer, the
eval counts of Ollama's) is recorded in the usage meter (clipforge.usage)
when the call runs inside a job or recording() context.

Failures raise LLMError. Credentials never appear in logs or error messages
(clipforge.llm_http sends the requests).
"""

import logging
import subprocess
from typing import Protocol, runtime_checkable

import httpx

from clipforge import __version__, config, usage
from clipforge.config import DEFAULT_COPILOT_ACCOUNT, Settings
from clipforge.llm_anthropic import AnthropicClient
from clipforge.llm_claude_code import ClaudeCodeClient
from clipforge.llm_http import LLMError, get_json, join_url, post_json
from clipforge.llm_models import (
    CopilotModels,
    OllamaTags,
    OpenAIModels,
    copilot_ids,
    ollama_ids,
    openai_ids,
)
from clipforge.llm_replies import ChatCompletion, OllamaChat, reply_json
from clipforge.llm_responses import (
    ModelList,
    ResponsesReply,
    model_endpoints,
    responses_body,
    responses_only,
)

__all__ = [
    "CopilotClient",
    "LLMClient",
    "LLMError",
    "ModelLister",
    "OllamaClient",
    "AnthropicClient",
    "ClaudeCodeClient",
    "OpenAICompatClient",
    "chat_messages",
    "create_client",
    "gh_auth_token",
    "model_of",
    "reply_json",
]

logger = logging.getLogger(__name__)

COPILOT_BASE_URL = "https://api.githubcopilot.com"
COPILOT_INTEGRATION_ID = "vscode-chat"
EDITOR_VERSION = f"clipforge/{__version__}"
GH_HOST = "github.com"
GH_TIMEOUT_S = 30.0


@runtime_checkable
class LLMClient(Protocol):
    """A chat model that answers in JSON."""

    def complete_json(self, system: str, user: str) -> str:
        """Return the model's reply to the two messages: JSON text, unparsed."""
        ...


@runtime_checkable
class ModelLister(Protocol):
    """A client that can list the models it serves (not Claude Code)."""

    def list_models(self) -> list[str]:
        """Return the ids of the models that can be asked."""
        ...


def chat_messages(system: str, user: str) -> list[dict[str, str]]:
    """Return the chat messages of a request: the system, then the user one."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def gh_auth_token(user: str, host: str = GH_HOST) -> str:
    """Return the GitHub CLI's token of account user on host.

    Runs `gh auth token -u <user> -h <host>` (no -u when user is empty: the
    active account). Raises LLMError if gh is not
    installed, fails (for example, the account is not logged in), times out,
    or prints no token.
    """
    command = ["gh", "auth", "token", *(["-u", user] if user else []), "-h", host]
    who = f" as {user}" if user else ""
    hint = f"set GITHUB_COPILOT_TOKEN or run `gh auth login -h {host}`{who}"
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=GH_TIMEOUT_S, check=False
        )
    except OSError as exc:
        raise LLMError(f"copilot: no token: cannot run gh ({exc}); {hint}") from exc
    except subprocess.TimeoutExpired:
        raise LLMError(
            f"copilot: no token: `gh auth token` took over {GH_TIMEOUT_S:.0f}s"
        ) from None
    token = result.stdout.strip()
    if result.returncode != 0 or not token:
        detail = " ".join(result.stderr.split()) or f"exit code {result.returncode}"
        raise LLMError(f"copilot: no token: {detail}; {hint}")
    return token


class OpenAICompatClient:
    """An OpenAI-compatible chat API: POST {base_url}/chat/completions with
    response_format json_object, and the API key (if any) as a Bearer token.
    """

    provider = "openai"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.url = join_url(base_url, "chat/completions")
        self.models_url = join_url(base_url, "models")
        self.model = model
        self._api_key = api_key
        self._transport = transport

    def complete_json(self, system: str, user: str) -> str:
        """Return the model's reply text (JSON mode) to the two messages."""
        key = self._credential()
        body = {
            "model": self.model,
            "messages": chat_messages(system, user),
            "response_format": {"type": "json_object"},
        }
        reply = post_json(
            self.provider,
            self.url,
            body,
            ChatCompletion,
            headers=self._headers(key),
            secret=key,
            transport=self._transport,
        )
        if reply.usage is not None:
            usage.record_tokens(reply.usage.total())
        return reply.choices[0].message.content

    def list_models(self) -> list[str]:
        """Return the ids of GET {base_url}/models."""
        key = self._credential()
        return openai_ids(
            get_json(
                self.provider,
                self.models_url,
                OpenAIModels,
                headers=self._headers(key),
                secret=key,
                transport=self._transport,
            )
        )

    def _credential(self) -> str:
        """Return the API key; an empty key sends no Authorization header."""
        return self._api_key

    def _headers(self, key: str) -> dict[str, str]:
        """Return the request headers that carry key."""
        return {"Authorization": f"Bearer {key}"} if key else {}


class CopilotClient(OpenAICompatClient):
    """GitHub Copilot's chat API (SPEC 13.1), with the OpenAI request shape.

    The token is GITHUB_COPILOT_TOKEN when given, else the GitHub CLI's token
    of account (COPILOT_ACCOUNT), fetched on the first request and then kept.
    """

    provider = "copilot"

    def __init__(
        self,
        model: str,
        token: str = "",
        *,
        account: str = DEFAULT_COPILOT_ACCOUNT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(COPILOT_BASE_URL, token, model, transport=transport)
        self.account = account

    def complete_json(self, system: str, user: str) -> str:
        """Return the reply text: from POST /responses if Copilot serves the
        model only there, else from POST /chat/completions."""
        key = self._credential()
        if not self._responses_only(key):
            return super().complete_json(system, user)
        reply = post_json(
            self.provider,
            join_url(COPILOT_BASE_URL, "responses"),
            responses_body(self.model, chat_messages(system, user)),
            ResponsesReply,
            headers=self._headers(key),
            secret=key,
            transport=self._transport,
        )
        if reply.usage is not None:
            usage.record_tokens(reply.usage.total_tokens)
        return reply.text()

    def list_models(self) -> list[str]:
        """Return the ids of the account's chat models (GET /models)."""
        key = self._credential()
        return copilot_ids(
            get_json(
                self.provider,
                self.models_url,
                CopilotModels,
                headers=self._headers(key),
                secret=key,
                transport=self._transport,
            )
        )

    def _responses_only(self, key: str) -> bool:
        """Whether the model list (GET /models, fetched once) says the model
        is served only at /responses; False if the list cannot be fetched."""
        url = join_url(COPILOT_BASE_URL, "models")
        headers = self._headers(key)
        try:
            endpoints = model_endpoints(
                url,
                key,
                lambda: get_json(
                    self.provider,
                    url,
                    ModelList,
                    headers=headers,
                    secret=key,
                    transport=self._transport,
                ),
            )
        except LLMError as exc:
            logger.warning("%s; using chat completions", exc)
            return False
        return responses_only(endpoints, self.model)

    def _credential(self) -> str:
        """Return the token, asking gh for it when none was given."""
        if not self._api_key:
            self._api_key = gh_auth_token(self.account)
        return self._api_key

    def _headers(self, key: str) -> dict[str, str]:
        """Return the headers Copilot's API needs, with key as Bearer token."""
        return {
            "Authorization": f"Bearer {key}",
            "Copilot-Integration-Id": COPILOT_INTEGRATION_ID,
            "Editor-Version": EDITOR_VERSION,
        }


class OllamaClient:
    """An Ollama server: POST {host}/api/chat with format json, no streaming."""

    provider = "ollama"

    def __init__(
        self, host: str, model: str, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.url = join_url(host, "api/chat")
        self.tags_url = join_url(host, "api/tags")
        self.model = model
        self._transport = transport

    def list_models(self) -> list[str]:
        """Return the names of the models on the server (GET /api/tags)."""
        return ollama_ids(
            get_json(
                self.provider,
                self.tags_url,
                OllamaTags,
                headers={},
                secret="",
                transport=self._transport,
            )
        )

    def complete_json(self, system: str, user: str) -> str:
        """Return the model's reply text (JSON format) to the two messages."""
        body = {
            "model": self.model,
            "messages": chat_messages(system, user),
            "format": "json",
            "stream": False,
        }
        reply = post_json(
            self.provider,
            self.url,
            body,
            OllamaChat,
            headers={},
            secret="",
            transport=self._transport,
        )
        usage.record_tokens(reply.prompt_eval_count + reply.eval_count)
        return reply.message.content


def create_client(
    cfg: Settings | None = None, *, transport: httpx.BaseTransport | None = None
) -> LLMClient:
    """Return the client of cfg.llm_provider (LLM_PROVIDER) for model_of(cfg).

    cfg defaults to the app settings. transport, if given, carries the HTTP
    requests instead of the network (httpx.MockTransport in tests).
    """
    cfg = config.settings if cfg is None else cfg
    if cfg.llm_provider == "copilot":
        return CopilotClient(
            cfg.llm_model,
            cfg.github_copilot_token,
            account=cfg.copilot_account,
            transport=transport,
        )
    if cfg.llm_provider == "openai":
        return OpenAICompatClient(
            cfg.openai_base_url,
            cfg.openai_api_key,
            cfg.llm_model,
            transport=transport,
        )
    if cfg.llm_provider == "anthropic":
        return AnthropicClient(
            cfg.anthropic_base_url,
            cfg.anthropic_api_key,
            cfg.anthropic_model,
            transport=transport,
        )
    if cfg.llm_provider == "claude_code":
        return ClaudeCodeClient(cfg.claude_code_bin, cfg.claude_code_model)
    return OllamaClient(cfg.ollama_host, cfg.llm_model, transport=transport)


def model_of(cfg: Settings) -> str:
    """Return the model that create_client(cfg) asks: ANTHROPIC_MODEL for
    the anthropic provider, CLAUDE_CODE_MODEL for claude_code, LLM_MODEL for
    the others."""
    if cfg.llm_provider == "anthropic":
        return cfg.anthropic_model
    if cfg.llm_provider == "claude_code":
        return cfg.claude_code_model
    return cfg.llm_model
