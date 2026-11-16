"""The messages of the Pro Edit critic (SPEC-v3 3.7) and the reply it must
send.

The system prompt is prompts/proedit_critic.md with the checklist (CHECKS:
each point's id and what it judges, in SPEC-v3 3.7's order), CriticReply's
JSON Schema (the scores and the EDL changes, changes.CriticChange) and the
params schema and track of every kind. The user message is one compact JSON
object: the preset (with the kinds it may use) and intensity, the passing
score, the clip's length and fps, one row per frame image (same order as
the images), the audio summary, the transcript and punchlines, the EDL and
the asset catalog (ids and tags). A retry adds the problems of the previous
reply.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from clipforge.models import CRITIC_SCORE_MAX, ProEditPlan
from clipforge.pipeline.curate_prompt import PROMPTS_DIR, fill
from clipforge.proedit.config import ProEditConfig
from clipforge.proedit.critic.audio_summary import AudioSummary
from clipforge.proedit.critic.changes import CriticChange
from clipforge.proedit.critic.sample import SampledFrame
from clipforge.proedit.director_catalog import CatalogAsset
from clipforge.proedit.director_prompt import params_models
from clipforge.proedit.edl import TRACK_OF_KIND
from clipforge.proedit.preset_defs import PresetDef
from clipforge.proedit.signal_models import ProEditSignals

PROMPT = PROMPTS_DIR / "proedit_critic.md"
DIGITS = 3
COMPACT = (",", ":")
DEFAULT_THRESHOLD = ProEditConfig().critic_threshold

CheckId = Literal[
    "hook",
    "dead_air",
    "captions",
    "crop_faces",
    "effect_balance",
    "audio_balance",
    "punchline",
    "loop_ending",
    "preset_faithfulness",
]
CHECKS: dict[CheckId, str] = {
    "hook": "Hook strength: do the first 2 s stop the scroll (motion, text, "
    "sound, a strong first line)?",
    "dead_air": "Dead air: no stretch without speech, movement or sound that drags.",
    "captions": "Caption sync and readability: captions match the spoken "
    "words, are legible and do not cover faces.",
    "crop_faces": "Crop and face errors: faces stay in the frame and are not "
    "cut by zooms, pans, shakes or overlays.",
    "effect_balance": "Effect use for the intensity: neither overused "
    "(effects pile up, distract) nor underused (flat for the intensity).",
    "audio_balance": "Audio balance: speech stays clearly above the music and "
    "sound effects; no clipping; loudness near -14 LUFS.",
    "punchline": "Punchline clarity: the punchline is heard and seen clearly, "
    "with nothing over the punchline word.",
    "loop_ending": "Loop ending: the end lands cleanly or loops back into the start.",
    "preset_faithfulness": "Preset faithfulness: the edit has the preset's "
    "look and moves.",
}
assert set(CHECKS) == set(get_args(CheckId))


class CriticScoreReply(BaseModel):
    """One checklist point of the reply."""

    model_config = ConfigDict(extra="forbid")

    check: CheckId
    score: float = Field(ge=0, le=CRITIC_SCORE_MAX)
    reason: str = Field(min_length=1)


class CriticReply(BaseModel):
    """The critic's scores (every checklist point exactly once) and the EDL
    changes that would raise the low ones (none when all pass)."""

    model_config = ConfigDict(extra="forbid")

    scores: list[CriticScoreReply]
    changes: list[CriticChange] = Field(default_factory=list)

    @model_validator(mode="after")
    def _every_check_once(self) -> Self:
        seen = [s.check for s in self.scores]
        missing = [c for c in CHECKS if c not in seen]
        twice = sorted({c for c in seen if seen.count(c) > 1})
        problems = []
        if missing:
            problems.append(f"missing checks: {', '.join(missing)}")
        if twice:
            problems.append(f"checks scored more than once: {', '.join(twice)}")
        if problems:
            raise ValueError("; ".join(problems))
        return self


@dataclass(frozen=True)
class CriticRequest:
    """What the critic judges: the plan the proxy was rendered from, its
    preset, the clip's signals, the sampled frames and the audio summary;
    the score every check must reach and the assets a change may name."""

    plan: ProEditPlan
    preset: PresetDef
    signals: ProEditSignals
    frames: Sequence[SampledFrame]
    audio: AudioSummary
    threshold: float = DEFAULT_THRESHOLD
    catalog: Sequence[CatalogAsset] = ()


def system_prompt() -> str:
    """Return the critic's system prompt."""
    checklist = "\n".join(f"- {check}: {text}" for check, text in CHECKS.items())
    params = {
        kind: m.model_json_schema() for kind, m in sorted(params_models().items())
    }
    return fill(
        PROMPT,
        {
            "checklist": checklist,
            "schema": json.dumps(CriticReply.model_json_schema(), indent=2),
            "params": json.dumps(params, separators=COMPACT, ensure_ascii=False),
            "tracks": json.dumps(
                dict(sorted(TRACK_OF_KIND.items())), separators=COMPACT
            ),
        },
    )


def _r(t: float) -> float:
    return round(t, DIGITS)


def critic_input(request: CriticRequest) -> dict[str, Any]:
    """Return the user message's JSON object (module docstring)."""
    plan, signals = request.plan, request.signals
    return {
        "preset": {
            "id": plan.preset,
            "name": request.preset.name,
            "description": request.preset.description,
            "kinds": sorted(request.preset.kinds),
        },
        "intensity": plan.intensity,
        "threshold": request.threshold,
        "clip": {"duration": _r(signals.duration), "fps": signals.fps},
        "frames": [
            {"image": n, "t": _r(f.sample.t), "why": list(f.sample.reasons)}
            for n, f in enumerate(request.frames, start=1)
        ],
        "audio": request.audio.model_dump(mode="json"),
        "transcript": [[_r(w.start), _r(w.end), w.text] for w in signals.words],
        "punchlines": [
            {"word": p.text, "span": [_r(p.start), _r(p.end)]}
            for p in signals.punchlines
        ],
        "edl": [
            {
                "id": item.id,
                "kind": item.kind,
                "t_start": _r(item.t_start),
                "t_end": _r(item.t_end),
                "params": item.params,
                "reason": item.reason,
            }
            for item in plan.items
        ],
        "catalog": [
            {"id": a.id, "kind": a.kind, "tags": a.tags} for a in request.catalog
        ],
    }


def user_prompt(request: CriticRequest, problems: Sequence[str] = ()) -> str:
    """Return the user message; problems (of the previous reply) ask for a
    corrected one."""
    text = json.dumps(critic_input(request), separators=COMPACT, ensure_ascii=False)
    if not problems:
        return text
    listed = "\n".join(f"- {problem}" for problem in problems)
    return (
        f"{text}\n\nYour previous reply was not valid:\n{listed}\n"
        "Send the whole reply again, corrected."
    )


def example_reply() -> str:
    """Return a reply as long as a typical one (for the cost estimate)."""
    reason = "x" * 160
    scores = [{"check": c, "score": 7, "reason": reason} for c in CHECKS]
    changes = [
        {"op": "modify", "item_id": 1, "t_start": 1.0, "reason": reason},
        {"op": "remove", "item_id": 2, "reason": reason},
    ]
    return json.dumps({"scores": scores, "changes": changes})
