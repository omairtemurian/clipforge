"""Settings endpoints (SPEC 8.7, PRD 11): read and change the settings that the
Settings page shows, and test the LLM connection."""

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Request
from pydantic import BaseModel

from clipforge import config, usage
from clipforge.api.errors import ApiError
from clipforge.config import Settings
from clipforge.llm import LLMError, ModelLister, create_client, model_of
from clipforge.settings_edit import (
    SECRET_FIELDS,
    SettingsConflict,
    SettingsInvalid,
    SettingsUpdate,
    SettingsView,
    save_settings,
    settings_view,
    with_changes,
)

logger = logging.getLogger(__name__)

router = APIRouter()

TEST_SYSTEM = "You are a connection test. Reply with JSON only."
TEST_USER = 'Reply with exactly {"ok": true}.'
REDACTED = "***"
# Per provider, the settings that make a different language model or reach
# it differently.
LLM_FIELDS = {
    "copilot": ("llm_model", "github_copilot_token", "copilot_account"),
    "openai": ("llm_model", "openai_base_url", "openai_api_key"),
    "ollama": ("llm_model", "ollama_host"),
    "anthropic": ("anthropic_model", "anthropic_base_url", "anthropic_api_key"),
    "claude_code": ("claude_code_model", "claude_code_bin"),
}
# How much of the model's reply the test shows.
REPLY_CHARS = 200


class LlmTestResult(BaseModel):
    """The outcome of a connection test: ok, and a message that is the
    start of the model's reply or the reason that it failed."""

    ok: bool
    provider: str
    model: str
    message: str


class LlmModels(BaseModel):
    """The models that the provider offers (the provider's own order), or why
    they could not be listed. A provider with no list (Claude Code) gives no
    models and no error."""

    models: list[str]
    error: str | None = None


@router.get("/settings")
def get_settings() -> SettingsView:
    """Return the settings; keys are shown only as set or not."""
    return settings_view(config.settings)


@router.put("/settings")
def put_settings(
    request: Request, update: SettingsUpdate, verify_llm: bool = False
) -> SettingsView:
    """Save the given settings (the others keep their value) and return all.

    422 if a value is not valid; 409 if an environment variable sets it.
    With verify_llm, a change of the language model (provider, model,
    endpoint or credentials) is first tried with one small request: if the
    model does not answer, nothing is saved and the answer is a 422 with the
    provider's error.
    """
    if verify_llm:
        _verify_llm(request, update)
    try:
        return settings_view(save_settings(update))
    except SettingsInvalid as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    except SettingsConflict as exc:
        raise ApiError(409, "conflict", str(exc)) from exc


@router.post("/settings/test-llm")
def test_llm(
    request: Request, update: Annotated[SettingsUpdate | None, Body()] = None
) -> LlmTestResult:
    """Send one small request to the LLM and report whether it answered.

    The body, if any, holds settings to try instead of the saved ones; it is
    not saved. A failure is a 200 with ok false and the reason, in which any
    key is replaced by ***.
    """
    try:
        cfg = with_changes({} if update is None else update.changes())
    except SettingsInvalid as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    return _try_llm(request, cfg)


def _verify_llm(request: Request, update: SettingsUpdate) -> None:
    """Raise a 422 with the provider's error unless the language model that
    update leads to answers; do nothing if update leaves it as it is."""
    try:
        cfg = with_changes(update.changes())
    except SettingsInvalid as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    current = config.settings
    fields = ("llm_provider", *LLM_FIELDS[cfg.llm_provider])
    if all(getattr(cfg, f) == getattr(current, f) for f in fields):
        return
    result = _try_llm(request, cfg)
    if not result.ok:
        raise ApiError(
            422,
            "llm_rejected",
            f"{result.provider} did not accept model {result.model}; "
            f"nothing was saved: {result.message}",
        )


def _try_llm(request: Request, cfg: Settings) -> LlmTestResult:
    """Send the one small request of the connection test with cfg."""
    try:
        with usage.recording(request.app.state.engine, None):
            reply = create_client(
                cfg, transport=request.app.state.llm_transport
            ).complete_json(TEST_SYSTEM, TEST_USER)
    except LLMError as exc:
        return _result(cfg, False, str(exc))
    return _result(cfg, True, reply)


def _result(cfg: Settings, ok: bool, message: str) -> LlmTestResult:
    """Return the test result with the message cut short and without keys."""
    for field in SECRET_FIELDS:
        secret: str = getattr(cfg, field)
        if secret:
            message = message.replace(secret, REDACTED)
    return LlmTestResult(
        ok=ok,
        provider=cfg.llm_provider,
        model=model_of(cfg),
        message=" ".join(message.split())[:REPLY_CHARS],
    )


@router.post("/settings/models")
def llm_models(
    request: Request, update: Annotated[SettingsUpdate | None, Body()] = None
) -> LlmModels:
    """List the models of the provider (Copilot's account, an OpenAI-compatible
    API, Ollama or Anthropic) for the Settings page's model picker, with the
    saved settings or the ones in the body (not saved). A failure (no key, a
    refused key, no connection) is a 200 with no models and the reason,
    without any key."""
    try:
        cfg = with_changes({} if update is None else update.changes())
    except SettingsInvalid as exc:
        raise ApiError(422, "validation_error", str(exc)) from exc
    client = create_client(cfg, transport=request.app.state.llm_transport)
    if not isinstance(client, ModelLister):
        return LlmModels(models=[])
    try:
        return LlmModels(models=client.list_models())
    except LLMError as exc:
        return LlmModels(models=[], error=_result(cfg, False, str(exc)).message)
