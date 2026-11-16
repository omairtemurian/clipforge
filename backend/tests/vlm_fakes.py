"""A fake Ollama server with a vision model, for the frame captions tests
(engines/vlm_ollama, pipeline/frame_captions, pipeline/visuals)."""

from collections.abc import Sequence

import httpx
import pytest
import respx
from clipforge import config

HOST = "http://vlm.test:11434"
MODEL = "qwen3.5-35b-128k:latest"
CAPTIONS = tuple(f" Frame\n{i}. " for i in range(3))


def use_server(monkeypatch: pytest.MonkeyPatch, vlm_model: str = "") -> None:
    """Point the settings at the fake server HOST, with VLM_MODEL vlm_model."""
    update = {"ollama_host": HOST, "vlm_model": vlm_model}
    monkeypatch.setattr(config, "settings", config.settings.model_copy(update=update))


def mock_ollama(
    respx_mock: respx.MockRouter, captions: Sequence[str] = CAPTIONS
) -> respx.Route:
    """Ollama at HOST with the vision model MODEL; returns the chat route,
    which answers the captions in turn, one per request."""
    respx_mock.get(f"{HOST}/api/version").respond(json={"version": "0.34.4"})
    respx_mock.get(f"{HOST}/api/tags").respond(json={"models": [{"name": MODEL}]})
    respx_mock.post(f"{HOST}/api/show").respond(
        json={"capabilities": ["completion", "vision"]}
    )
    replies = [
        httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": caption},
                "prompt_eval_count": 171,
                "eval_count": 9,
            },
        )
        for caption in captions
    ]
    return respx_mock.post(f"{HOST}/api/chat").mock(side_effect=replies)
