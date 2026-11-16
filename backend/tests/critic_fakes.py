"""Shared fakes of the Pro Edit critic tests (tests only): an LLM server that
answers each request with the next recorded reply, a valid critic reply and
a critic request built without rendering."""

import io
import json
from collections import deque
from pathlib import Path
from typing import Any

import httpx
from clipforge.models import EdlItem, ProEditPlan
from clipforge.proedit.critic.audio_summary import AudioSummary
from clipforge.proedit.critic.prompt import CHECKS, CriticRequest
from clipforge.proedit.critic.sample import FrameSample, SampledFrame
from clipforge.proedit.critic.vision import Image
from clipforge.proedit.preset_defs import get_preset
from clipforge.proedit.signal_models import ProEditSignals
from PIL import Image as PILImage

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SIGNALS = ProEditSignals.model_validate(
    json.loads((FIXTURES / "proedit_signals_expected.json").read_text())
)
SEES_RED = '{"color": "red"}'
FRAME_SIZE = (90, 160)


class ReplyServer:
    """An LLM HTTP server that answers each POST with the next reply (a JSON
    body, or an HTTP status for a failure) and keeps the requests. GET
    .../models (Copilot's model list) answers {"data": models}."""

    def __init__(
        self, *replies: dict[str, Any] | int, models: list[dict[str, Any]] | None = None
    ) -> None:
        self.replies: deque[dict[str, Any] | int] = deque(replies)
        self.models = models or []
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def body(self, n: int) -> dict[str, Any]:
        """Return the JSON body of request n."""
        body: dict[str, Any] = json.loads(self.requests[n].content)
        return body

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": self.models, "object": "list"})
        self.requests.append(request)
        reply = self.replies.popleft()
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": {"message": "nope"}})
        return httpx.Response(200, json=reply)


def scores_reply(**scores: float) -> str:
    """Return a valid critic reply: every check scores 8 unless scores says
    otherwise."""
    return json.dumps(
        {
            "scores": [
                {"check": c, "score": scores.get(c, 8), "reason": f"{c} at 1.2 s"}
                for c in reversed(list(CHECKS))
            ]
        }
    )


def jpeg(rgb: tuple[int, int, int], size: tuple[int, int] = FRAME_SIZE) -> Image:
    """Return a JPEG of size filled with rgb."""
    buffer = io.BytesIO()
    PILImage.new("RGB", size, rgb).save(buffer, "JPEG")
    return Image(buffer.getvalue(), "image/jpeg")


def frames(*times: float) -> list[SampledFrame]:
    """Return 30-fps frame samples at times with small gray images."""
    return [
        SampledFrame(
            FrameSample(round(t * 30), t, ("1 fps baseline",)),
            jpeg((n * 40, n * 40, n * 40)),
            *FRAME_SIZE,
        )
        for n, t in enumerate(times)
    ]


def audio() -> AudioSummary:
    """Return the audio summary of a well-mixed edit."""
    return AudioSummary(
        integrated_lufs=-14.1,
        true_peak_dbtp=-1.2,
        peak_dbfs=-1.5,
        clipped_samples=0,
        loudness_curve=[-20.0, -18.5],
        speech_db=-17.0,
        music_db=-30.0,
        sfx_db=-19.0,
        speech_over_music_db=13.0,
    )


def critic_request(n_frames: int = 3) -> CriticRequest:
    """Return a critic request of the signals fixture with a two-item plan."""
    items = [
        EdlItem(id=1, kind="zoom_punch", t_start=0.0, t_end=1.0, reason="hook"),
        EdlItem(
            id=2,
            kind="text_pop",
            t_start=2.0,
            t_end=3.0,
            params={"text": "WOW"},
            reason="punchline",
        ),
    ]
    plan = ProEditPlan(
        id=1,
        clip_id=SIGNALS.clip_id,
        preset="phonk_edit",
        intensity="pro",
        version=1,
        items=items,
        created_by="director",
    )
    return CriticRequest(
        plan=plan,
        preset=get_preset("phonk_edit"),
        signals=SIGNALS,
        frames=frames(*[float(n) for n in range(n_frames)]),
        audio=audio(),
    )
