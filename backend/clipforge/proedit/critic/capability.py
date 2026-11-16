"""Whether the configured LLM accepts images (SPEC-v3 1.6, 3.7): the critic
runs only when it does; otherwise Pro Edit runs the Director only and the UI
shows VisionCheck.message.

check_vision sends one probe per model (provider, endpoint and model): a
small image filled with PROBE_COLOR and the question which color fills it.
The model accepts images when its reply names that color. A provider with no
image request shape (Claude Code) is not asked. A server that refuses the
request (HTTP 400, 413, 415 or 422: the model takes no images) or a reply
that misses the color means no. The answer is kept for the life of the
process; a request that fails otherwise (no connection, 401, 429, 5xx) is
not kept, so the next run asks again.
"""

import io
import logging
import re
import threading
from dataclasses import dataclass

from PIL import Image as PILImage

from clipforge.llm import LLMClient, LLMError
from clipforge.proedit.critic.vision import (
    Image,
    can_send_images,
    complete_with_images,
    model_key,
)

logger = logging.getLogger(__name__)

PROBE_RGB = (220, 20, 20)
PROBE_COLOR = "red"
PROBE_SIZE = 64
PROBE_SYSTEM = "You look at images and answer with one JSON object only."
PROBE_USER = 'Which color fills this image? Answer {"color": "<one English word>"}.'
REFUSED = frozenset({400, 413, 415, 422})
DIRECTOR_ONLY = "Pro Edit runs the Director only (no critic)."

_checked: dict[tuple[str, str, str], "VisionCheck"] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class VisionCheck:
    """Whether the critic can run with the model, and the UI message that
    says why not (None when it can)."""

    vision: bool
    message: str | None = None

    @property
    def director_only(self) -> bool:
        """Whether Pro Edit must run without the critic."""
        return not self.vision


def probe_image() -> Image:
    """Return the probe: a PNG filled with PROBE_RGB."""
    buffer = io.BytesIO()
    PILImage.new("RGB", (PROBE_SIZE, PROBE_SIZE), PROBE_RGB).save(buffer, "PNG")
    return Image(buffer.getvalue(), "image/png")


def check_vision(llm: LLMClient | None) -> VisionCheck:
    """Return whether llm accepts images (module docstring)."""
    if llm is None:
        return VisionCheck(False, f"No LLM is configured: {DIRECTOR_ONLY}")
    key = model_key(llm)
    with _lock:
        known = _checked.get(key)
    if known is not None:
        return known
    check, keep = _probe(llm, key)
    if keep:
        with _lock:
            _checked[key] = check
    return check


def clear_vision_cache() -> None:
    """Forget every probe answer (tests, or after the owner changes model)."""
    with _lock:
        _checked.clear()


def _probe(llm: LLMClient, key: tuple[str, str, str]) -> tuple[VisionCheck, bool]:
    provider, _, model = key
    if not can_send_images(llm):
        message = f"The {provider} provider cannot send images: {DIRECTOR_ONLY}"
        return VisionCheck(False, message), True
    try:
        reply = complete_with_images(llm, PROBE_SYSTEM, PROBE_USER, [probe_image()])
    except LLMError as error:
        if error.status_code in REFUSED:
            message = f"The model {model} does not accept images: {DIRECTOR_ONLY}"
            logger.info("%s refused the image probe: %s", model, error)
            return VisionCheck(False, message), True
        message = f"Could not check whether {model} accepts images ({error}): "
        return VisionCheck(False, message + DIRECTOR_ONLY), False
    if re.search(rf"\b{PROBE_COLOR}\b", reply.lower()) is None:
        logger.info("%s did not see the probe image: %r", model, reply[:200])
        message = f"The model {model} does not see images: {DIRECTOR_ONLY}"
        return VisionCheck(False, message), True
    return VisionCheck(True), True
