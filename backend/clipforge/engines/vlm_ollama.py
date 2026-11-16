"""The vision-language model engine (SPEC-v2 3.2): a local Ollama server
with a model that has the vision capability describes video frames.

The server's models are those of `ollama list` (GET /api/tags); a model is
a vision model when POST /api/show lists "vision" in its `capabilities`.
The engine uses VLM_MODEL, or the first vision model when that is empty.
`VisionCaptioner` sends one JPEG frame (base64, in the user message's
`images`) to POST /api/chat with stream false and think false, so that a
thinking model (qwen3.5) answers at once, and returns the reply text.
API checked against docs.ollama.com/api (docs/decisions.md "TASK-78").
"""

import base64
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from clipforge import config, usage
from clipforge.engines.base import Engine, InstallStatus
from clipforge.llm_http import LLMError, join_url, post_json
from clipforge.llm_replies import OllamaChat

OLLAMA_TIMEOUT_S = 5.0
PROVIDER = "ollama-vlm"
DEFAULT_TAG = ":latest"
CAPTION_PROMPT = (
    "This is one frame of a video. In one short sentence, say who or what is "
    "visible and what is happening; quote any large on-screen text. "
    "Answer with the sentence only."
)
CAPTION_MAX_TOKENS = 80


@dataclass(frozen=True)
class OllamaModels:
    """What an Ollama server holds: its version and its vision models, in
    the order of `ollama list`."""

    version: str
    vision: list[str]


def full_name(model: str) -> str:
    """Return model with the tag Ollama gives a name without one (latest)."""
    return model if ":" in model else model + DEFAULT_TAG


def ollama_models(
    host: str, transport: httpx.BaseTransport | None = None
) -> OllamaModels:
    """Ask the Ollama server at host for its version and vision models.

    Raises httpx.HTTPError if it cannot be reached or fails, and KeyError,
    TypeError or ValueError if it answers something unexpected.
    """
    with httpx.Client(
        base_url=host.rstrip("/"), timeout=OLLAMA_TIMEOUT_S, transport=transport
    ) as client:
        version = str(_get(client, "/api/version")["version"])
        tags = _get(client, "/api/tags")["models"]
        vision = [m["name"] for m in tags if _has_vision(client, m["name"])]
    return OllamaModels(version, vision)


def _get(client: httpx.Client, path: str) -> dict[str, Any]:
    reply = client.get(path)
    reply.raise_for_status()
    body: dict[str, Any] = reply.json()
    return body


def _has_vision(client: httpx.Client, model: str) -> bool:
    reply = client.post("/api/show", json={"model": model})
    reply.raise_for_status()
    return "vision" in reply.json().get("capabilities", [])


def pick_model(wanted: str, vision: list[str]) -> str | None:
    """Return the vision model to use: wanted (VLM_MODEL) if it is one of
    vision, the first of vision if wanted is empty, else None."""
    if not wanted:
        return vision[0] if vision else None
    name = full_name(wanted)
    return name if name in {full_name(v) for v in vision} else None


class OllamaVisionEngine(Engine):
    """A local Ollama server with a vision model (VLM_MODEL if set). The
    version is the server's. `transport` replaces the network (tests)."""

    def __init__(
        self, name: str, label: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        super().__init__(name, label)
        self.transport = transport

    def install_check(self) -> InstallStatus:
        host = config.settings.ollama_host
        try:
            found = ollama_models(host, self.transport)
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return InstallStatus(
                installed=False, error=f"no Ollama server at {host} (ollama serve)"
            )
        if not found.vision:
            return InstallStatus(
                installed=False,
                version=found.version,
                error="Ollama has no model with the vision capability (ollama pull)",
            )
        wanted = config.settings.vlm_model
        if pick_model(wanted, found.vision) is None:
            return InstallStatus(
                installed=False,
                version=found.version,
                error=f"VLM_MODEL {wanted} is not a pulled vision model "
                f"(ollama pull {wanted})",
            )
        return InstallStatus(installed=True, version=found.version)


class Captioner(Protocol):
    """Something that describes one video frame: `model` names it."""

    model: str

    def caption(self, jpeg: bytes) -> str:
        """Return a one-line description of the JPEG image jpeg."""
        ...


class VisionCaptioner:
    """An Ollama vision model at host that captions frames."""

    def __init__(
        self, host: str, model: str, *, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.url = join_url(host, "api/chat")
        self.model = model
        self._transport = transport

    def caption(self, jpeg: bytes) -> str:
        """Return the model's one-line description of the JPEG image jpeg.

        Raises LLMError if the server fails or the reply is empty.
        """
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": CAPTION_PROMPT,
                    "images": [base64.b64encode(jpeg).decode("ascii")],
                }
            ],
            "stream": False,
            "think": False,
            "options": {"temperature": 0, "num_predict": CAPTION_MAX_TOKENS},
        }
        reply = post_json(
            PROVIDER,
            self.url,
            body,
            OllamaChat,
            headers={},
            secret="",
            transport=self._transport,
        )
        usage.record_tokens(reply.prompt_eval_count + reply.eval_count)
        text = " ".join(reply.message.content.split())
        if not text:
            raise LLMError(f"{PROVIDER}: {self.model} returned an empty caption")
        return text


def create_captioner(transport: httpx.BaseTransport | None = None) -> VisionCaptioner:
    """Return the captioner of the configured server and vision model
    (VLM_MODEL, or the first vision model). Raises LLMError if the server
    cannot be reached or has no such model."""
    host = config.settings.ollama_host
    try:
        found = ollama_models(host, transport)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise LLMError(f"{PROVIDER}: no Ollama server at {host}: {exc}") from exc
    model = pick_model(config.settings.vlm_model, found.vision)
    if model is None:
        raise LLMError(f"{PROVIDER}: no vision model on the Ollama server at {host}")
    return VisionCaptioner(host, model, transport=transport)
