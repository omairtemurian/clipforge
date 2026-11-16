"""Style recipes from their references' features (SPEC-v3 4.4, 4.5).

Aggregation: for each metric (style/metrics) the median, lowest and
highest value over the references that have it, rounded to DECIMALS; the
caption color is the per-channel median of the references' colors.

Description: a short text about the targets written by the LLM, or by
describe_rules when the LLM cannot be reached or its reply is not valid.

Style-match score of a measured video against a recipe: for each metric of
the recipe that the video has, with v the measured value and [low, high]
the recipe's range,

    width   = max(high - low, tolerance of the metric)
    outside = max(low - v, v - high, 0)
    score   = max(0, 1 - outside / width)

so a value inside the range scores 1 and one a range width (at least the
tolerance) outside it scores 0. The match is the mean over the compared
metrics (None without any); the 0-100 score is round(100 * match).
"""

import json
import statistics
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import Engine

from clipforge.llm import LLMClient, LLMError, reply_json
from clipforge.models import (
    StyleMetricMatch,
    StyleRecipe,
    StyleRecipeExport,
    StyleTarget,
    StyleTargets,
)
from clipforge.proedit.config import ProEditConfig
from clipforge.proedit.director_cost import metered
from clipforge.proedit.style.metrics import (
    METRIC_BY_KEY,
    METRICS,
    Features,
    caption_color,
    metric_values,
)

DECIMALS = 4
MAX_DESCRIPTION = 400
LOOP_ENDING_SHARE = 0.5
DESCRIBE_SYSTEM = (
    "You describe the editing style of short vertical videos for a video "
    "editor. You get the target numbers of a style (medians and ranges over "
    "reference videos). Reply with only a JSON object "
    '{"description": "..."}: one or two plain sentences, under 300 '
    "characters, saying what the edit feels like (pace, motion, look, "
    "effects, captions, sound). Use only the numbers given."
)


class _Description(BaseModel):
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION)


def aggregate(references: Iterable[Features]) -> StyleTargets:
    """Return the targets of the references' features (module doc)."""
    values: dict[str, list[float]] = {}
    colors: list[str] = []
    for features in references:
        for key, value in metric_values(features).items():
            values.setdefault(key, []).append(value)
        color = caption_color(features)
        if color is not None:
            colors.append(color)
    metrics = {
        metric.key: StyleTarget(
            median=round(statistics.median(found), DECIMALS),
            low=round(min(found), DECIMALS),
            high=round(max(found), DECIMALS),
            count=len(found),
        )
        for metric in METRICS
        if (found := values.get(metric.key))
    }
    return StyleTargets(metrics=metrics, caption_color=_median_color(colors))


def _median_color(colors: list[str]) -> str | None:
    if not colors:
        return None
    channels = [[int(color[i : i + 2], 16) for color in colors] for i in (1, 3, 5)]
    return "#" + "".join(f"{round(statistics.median(c)):02x}" for c in channels)


def targets_of(recipe: StyleRecipe) -> StyleTargets:
    """Return the targets stored in recipe (none before an analysis)."""
    return StyleTargets.model_validate(recipe.features.get("targets") or {})


def check_targets(targets: StyleTargets) -> None:
    """Raise ValueError if targets name a metric that does not exist."""
    unknown = sorted(set(targets.metrics) - set(METRIC_BY_KEY))
    if unknown:
        raise ValueError(f"unknown style metric(s): {', '.join(unknown)}")


def target_summary(targets: StyleTargets) -> dict[str, Any]:
    """Return the targets as the Director and the describing LLM read
    them: per metric its label, unit, target (the median) and range."""
    return {
        "metrics": {
            key: {
                "label": METRIC_BY_KEY[key].label,
                "unit": METRIC_BY_KEY[key].unit,
                "target": target.median,
                "low": target.low,
                "high": target.high,
            }
            for key, target in targets.metrics.items()
            if key in METRIC_BY_KEY
        },
        "caption_color": targets.caption_color,
    }


def director_recipe(recipe: StyleRecipe) -> dict[str, Any]:
    """Return what the Director reads of recipe: its name, description and
    target summary (never the per-reference features)."""
    return {
        "name": recipe.name,
        "description": recipe.description,
        "targets": target_summary(targets_of(recipe)),
    }


def _median(targets: StyleTargets, key: str) -> float | None:
    target = targets.metrics.get(key)
    return None if target is None else target.median


def _loops(targets: StyleTargets) -> bool:
    return (_median(targets, "loop_ending") or 0) >= LOOP_ENDING_SHARE


def recipe_loops(recipe: StyleRecipe) -> bool:
    """Whether the references of recipe mostly end on a loop (their median
    loop_ending at least LOOP_ENDING_SHARE): its edits get a loop-friendly
    ending (proedit/retention.py)."""
    return _loops(targets_of(recipe))


def _pace(targets: StyleTargets) -> list[str]:
    parts = []
    cuts = _median(targets, "cuts_per_minute")
    if cuts is not None:
        shot = _median(targets, "median_shot_s")
        shot_text = f" (shots of about {shot:.1f} s)" if shot else ""
        parts.append(f"{cuts:.0f} cuts a minute{shot_text}")
    on_beat = _median(targets, "cuts_on_beat")
    if on_beat:
        parts.append(f"{on_beat:.0%} of the cuts on the beat")
    for key, name in (
        ("punches_per_minute", "zoom punches"),
        ("shakes_per_minute", "shakes"),
        ("flashes_per_minute", "flashes"),
        ("glitches_per_minute", "glitches"),
    ):
        rate = _median(targets, key)
        if rate:
            parts.append(f"{rate:.0f} {name} a minute")
    return parts


def _look(targets: StyleTargets) -> list[str]:
    words = []
    luma = _median(targets, "mean_luma")
    if luma is not None:
        words.append("dark" if luma < 0.35 else "bright" if luma > 0.6 else "")
    saturation = _median(targets, "saturation")
    if saturation is not None:
        words.append(
            "desaturated"
            if saturation < 0.15
            else "saturated"
            if saturation > 0.45
            else ""
        )
    for key, word in (("vignette", "vignetted"), ("grain", "grainy")):
        if (_median(targets, key) or 0) >= 0.2:
            words.append(word)
    bw = _median(targets, "bw_share")
    look = ", ".join(word for word in words if word)
    parts = [f"a {look} look"] if look else []
    if bw and bw >= 0.05:
        parts.append(f"{bw:.0%} of it in black and white")
    return parts


def _sound(targets: StyleTargets) -> list[str]:
    parts = []
    words = _median(targets, "caption_words_per_line")
    if words is not None:
        upper = (_median(targets, "caption_uppercase") or 0) >= 0.6
        caps = " in capitals" if upper else ""
        parts.append(f"captions of {words:.0f} words a line{caps}")
    music = _median(targets, "music_share")
    if music is not None and music >= 0.3:
        bpm = _median(targets, "bpm")
        parts.append(f"music at {bpm:.0f} BPM" if bpm else "music under it")
    drops = _median(targets, "drops_per_minute")
    if drops:
        parts.append(f"{drops:.0f} drops a minute")
    if _loops(targets):
        parts.append("an ending that loops to the start")
    return parts


def describe_rules(targets: StyleTargets) -> str:
    """Return a short text about the targets, written by rules."""
    if not targets.metrics:
        return "No reference analyzed yet."
    sentences = [
        ", ".join(parts)
        for parts in (_pace(targets), _look(targets), _sound(targets))
        if parts
    ]
    text = ". ".join(s[0].upper() + s[1:] for s in sentences)
    return (text + ".") if text else "A calm edit with few effects."


def describe(
    name: str,
    targets: StyleTargets,
    llm: LLMClient | None,
    *,
    engine: Engine | None = None,
    cfg: ProEditConfig | None = None,
) -> str:
    """Return the LLM's short text about recipe name's targets, or
    describe_rules' when there is no llm, no target, or the LLM cannot be
    reached or does not reply valid JSON. With an engine the call is
    metered as Pro Edit use (cfg: its price)."""
    fallback = describe_rules(targets)
    if llm is None or not targets.metrics:
        return fallback
    user = json.dumps({"name": name, "targets": target_summary(targets)})
    try:
        with metered(engine, None, cfg or ProEditConfig(), []):
            reply = llm.complete_json(DESCRIBE_SYSTEM, user)
        return _Description.model_validate_json(reply_json(reply)).description
    except (LLMError, ValidationError):
        return fallback


class MatchResult(BaseModel):
    """The style-match of measured values against targets: the mean metric
    score (None without a compared metric) and each compared metric."""

    match: float | None
    metrics: list[StyleMetricMatch]

    @property
    def score(self) -> int | None:
        """The match as 0-100."""
        return None if self.match is None else round(100 * self.match)


def style_match(values: dict[str, float], targets: StyleTargets) -> MatchResult:
    """Return how well the measured metric values fit targets (module
    doc)."""
    compared = []
    for key, target in targets.metrics.items():
        metric = METRIC_BY_KEY.get(key)
        value = values.get(key)
        if metric is None or value is None:
            continue
        width = max(target.high - target.low, metric.tolerance)
        outside = max(target.low - value, value - target.high, 0.0)
        compared.append(
            StyleMetricMatch(
                key=key,
                label=metric.label,
                unit=metric.unit,
                value=round(value, DECIMALS),
                target=target,
                score=round(max(0.0, 1 - outside / width), DECIMALS),
            )
        )
    scores = [metric.score for metric in compared]
    match = round(statistics.mean(scores), DECIMALS) if scores else None
    return MatchResult(match=match, metrics=compared)


def export_recipe(recipe: StyleRecipe) -> StyleRecipeExport:
    """Return recipe as its export: name, description, reference count and
    targets only (no media, paths, links or per-reference features)."""
    return StyleRecipeExport(
        name=recipe.name,
        description=recipe.description,
        reference_count=recipe.reference_count,
        targets=targets_of(recipe),
    )
