"""Tests of style recipes from features (SPEC-v3 4.4, 4.5): the metrics read
from a reference's features, the aggregation (medians, ranges, caption
color), the rule-based and LLM descriptions, the style-match score and the
export without media."""

import json
from typing import Any

import pytest
from clipforge.llm_http import LLMError
from clipforge.models import StyleRecipe, StyleRecipeExport, StyleTarget, StyleTargets
from clipforge.proedit.style.metrics import METRICS, metric_values
from clipforge.proedit.style.recipe import (
    aggregate,
    check_targets,
    describe,
    describe_rules,
    director_recipe,
    export_recipe,
    style_match,
)
from pydantic import ValidationError
from style_recipe_fixtures import REFS, features


def test_every_metric_is_read_from_the_stored_features() -> None:
    values = metric_values(REFS[0])

    assert values == {
        "cuts_per_minute": 30.0,
        "median_shot_s": 2.0,
        "cuts_on_beat": 0.5,
        "punches_per_minute": 6.0,
        "punch_amplitude": 0.15,
        "ramps_per_minute": 0.0,
        "shakes_per_minute": 0.0,
        "mean_luma": 0.3,
        "contrast": 0.2,
        "saturation": 0.1,
        "bw_share": 0.0,
        "vignette": 0.3,
        "grain": 0.05,
        "flashes_per_minute": 4.0,
        "glitches_per_minute": 0.0,
        "caption_words_per_line": 2.0,
        "caption_size": 0.06,
        "caption_position_y": 0.7,
        "caption_uppercase": 1.0,
        "music_share": 0.8,
        "bpm": 140.0,
        "drops_per_minute": 4.0,
        "sfx_per_minute": 2.0,
        "time_to_first_effect": 0.4,
        "hook_s": 1.5,
        "effects_per_window": 4.0,
        "loop_ending": 1.0,
    }
    assert set(values) <= {metric.key for metric in METRICS}


def test_without_audio_or_captions_their_metrics_are_missing() -> None:
    bare = {**REFS[0], "audio": None, "captions": None}

    values = metric_values(bare)

    assert not {"bpm", "music_share", "drops_per_minute", "caption_size"} & set(values)
    assert values["cuts_per_minute"] == 30.0


def test_aggregation_gives_exact_medians_ranges_and_counts() -> None:
    targets = aggregate(REFS)

    metrics = targets.metrics
    assert metrics["cuts_per_minute"] == StyleTarget(
        median=30.0, low=18.0, high=42.0, count=3
    )
    assert metrics["median_shot_s"] == StyleTarget(
        median=2.0, low=1.4, high=3.1, count=3
    )
    assert metrics["mean_luma"] == StyleTarget(median=0.3, low=0.24, high=0.36, count=3)
    assert metrics["bpm"] == StyleTarget(median=145.0, low=140.0, high=150.0, count=2)
    assert metrics["vignette"] == StyleTarget(median=0.3, low=0.3, high=0.3, count=3)
    assert "zooms_on_beat" not in metrics
    assert list(metrics) == [m.key for m in METRICS if m.key in metrics]
    # per channel: r median(ff, ff, f0), g median(ff, d0, e0), b median(ff, 00, 00)
    assert targets.caption_color == "#ffe000"


def test_aggregating_nothing_gives_no_targets() -> None:
    assert aggregate([]) == StyleTargets()
    assert describe_rules(StyleTargets()) == "No reference analyzed yet."


def test_identical_features_match_fully_and_distant_ones_less() -> None:
    targets = aggregate([REFS[0]])
    near = features(33.0, 2.0, 0.30, 140.0, "#ffffff")
    far = features(90.0, 0.4, 0.80, 70.0, "#ffffff")

    same = style_match(metric_values(REFS[0]), targets)
    close = style_match(metric_values(near), targets)
    distant = style_match(metric_values(far), targets)

    assert same.match == 1.0
    assert same.score == 100
    assert len(same.metrics) == len(targets.metrics)
    assert all(metric.score == 1.0 for metric in same.metrics)
    assert distant.match is not None and close.match is not None
    assert distant.match < close.match < 1.0
    cuts = next(m for m in close.metrics if m.key == "cuts_per_minute")
    # 3 cuts/min outside a zero-width range: 1 - 3 / tolerance 6
    assert cuts.score == 0.5
    assert cuts.value == 33.0


def test_the_score_follows_the_documented_formula() -> None:
    targets = StyleTargets(
        metrics={
            "cuts_per_minute": StyleTarget(median=30, low=20, high=40, count=2),
            "mean_luma": StyleTarget(median=0.3, low=0.3, high=0.3),
            "bpm": StyleTarget(median=140, low=130, high=150),
        }
    )
    values = {"cuts_per_minute": 45.0, "mean_luma": 0.5, "grain": 0.9}

    result = style_match(values, targets)

    by_key = {metric.key: metric.score for metric in result.metrics}
    # cuts: 5 outside a 20 wide range -> 0.75; luma: 0.2 outside, tolerance
    # 0.05 -> 0; bpm and grain are not compared (not measured / no target)
    assert by_key == {"cuts_per_minute": 0.75, "mean_luma": 0.0}
    assert result.match == 0.375
    assert result.score == 38


def test_no_compared_metric_gives_no_score() -> None:
    result = style_match({}, aggregate(REFS))

    assert result.match is None
    assert result.score is None
    assert result.metrics == []


def test_the_rule_description_names_pace_look_and_sound() -> None:
    text = describe_rules(aggregate(REFS))

    assert text == (
        "30 cuts a minute (shots of about 2.0 s), 50% of the cuts on the beat, "
        "6 zoom punches a minute, 4 flashes a minute. "
        "A dark, desaturated, vignetted look. "
        "Captions of 2 words a line in capitals, music at 145 BPM, "
        "4 drops a minute, an ending that loops to the start."
    )


class ReplyLLM:
    """An LLM that answers reply and keeps what it was asked."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.users: list[str] = []

    def complete_json(self, system: str, user: str) -> str:
        self.users.append(user)
        return self.reply


class DownLLM:
    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("the LLM is offline")


def test_the_llm_writes_the_description_from_the_targets() -> None:
    llm = ReplyLLM('```json\n{"description": "Fast, dark phonk edit."}\n```')
    targets = aggregate(REFS)

    text = describe("Night phonk", targets, llm)

    assert text == "Fast, dark phonk edit."
    asked = json.loads(llm.users[0])
    assert asked["name"] == "Night phonk"
    assert asked["targets"]["metrics"]["cuts_per_minute"] == {
        "label": "Cuts",
        "unit": "/min",
        "target": 30.0,
        "low": 18.0,
        "high": 42.0,
    }


@pytest.mark.parametrize(
    "llm", [DownLLM(), ReplyLLM("not json"), ReplyLLM('{"description": ""}'), None]
)
def test_without_a_valid_llm_reply_the_rules_describe(llm: object) -> None:
    targets = aggregate(REFS)

    assert describe("Night phonk", targets, llm) == describe_rules(targets)  # type: ignore[arg-type]


def recipe(**features_: Any) -> StyleRecipe:
    return StyleRecipe(
        id=4,
        name="Night phonk",
        description="Fast cuts.",
        features=features_,
        reference_count=3,
        created_at="2026-11-08T10:00:00Z",  # type: ignore[arg-type]
    )


def test_the_export_holds_only_the_targets_never_media() -> None:
    stored = recipe(
        references={"7": {**REFS[0], "path": "/data/work/style_7/ref.mp4"}},
        targets=aggregate(REFS).model_dump(),
    )

    exported = export_recipe(stored).model_dump(mode="json")

    assert set(exported) == {
        "format",
        "version",
        "name",
        "description",
        "reference_count",
        "targets",
    }
    assert exported["format"] == "clipforge.style_recipe"
    text = json.dumps(exported)
    assert "/data" not in text and "style_7" not in text and ".mp4" not in text
    assert "http" not in text and "references" not in text
    assert StyleRecipeExport.model_validate(exported).targets == aggregate(REFS)


def test_an_import_with_anything_else_is_refused() -> None:
    exported = export_recipe(recipe(targets=aggregate(REFS).model_dump()))
    data = exported.model_dump(mode="json")

    with pytest.raises(ValidationError):
        StyleRecipeExport.model_validate({**data, "media": "/tmp/ref.mp4"})
    with pytest.raises(ValidationError):
        StyleRecipeExport.model_validate(
            {**data, "targets": {**data["targets"], "path": "/tmp"}}
        )
    with pytest.raises(ValidationError):
        StyleTarget(median=5, low=6, high=7)
    with pytest.raises(ValueError, match="unknown style metric"):
        check_targets(
            StyleTargets(metrics={"warp": StyleTarget(median=1, low=1, high=1)})
        )


def test_the_director_reads_the_targets_not_the_reference_features() -> None:
    stored = recipe(references={"7": REFS[0]}, targets=aggregate(REFS).model_dump())

    read = director_recipe(stored)

    assert set(read) == {"name", "description", "targets"}
    assert read["targets"]["metrics"]["bpm"]["target"] == 145.0
    assert read["targets"]["caption_color"] == "#ffe000"
    assert "references" not in json.dumps(read)
