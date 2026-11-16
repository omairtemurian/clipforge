"""Regression (TASK-237): the owner's Skull Moment run at Standard showed
no skull. The effects budget (budgets.enforce_budgets, 2 effects per 5 s at
standard, dropping by KIND_PRIORITY) cut the LLM's skull moment down to a
freeze and a boom, and the rule-based Director placed the sequence step by
step against the same budget, leaving the skull, punch-in and shake out.
The whole sequence must now survive at every intensity."""

import json

import pytest
from clipforge.models import ProEditIntensity
from clipforge.proedit.budgets import INTENSITIES
from clipforge.proedit.composites import find_composites
from clipforge.proedit.director_llm import director_plan
from clipforge.proedit.director_music import MusicChoice
from clipforge.proedit.director_rules import rule_plan
from clipforge.proedit.edl import validate_plan
from clipforge.proedit.preset_defs import get_preset
from fakes import FakeLLMClient
from skull_fakes import (
    CAUGHT,
    MUSIC,
    RECORDED_SKULL,
    SIGNALS,
    assert_whole_skull,
    skull_request,
)


@pytest.mark.parametrize("intensity", INTENSITIES)
@pytest.mark.parametrize("music", [None, MUSIC])
def test_the_rule_director_places_the_whole_skull_moment(
    intensity: ProEditIntensity, music: MusicChoice | None
) -> None:
    result = rule_plan(
        SIGNALS, get_preset("skull_moment"), "skull_moment", intensity, music
    )
    validate_plan(result.plan, SIGNALS.duration)
    assert_whole_skull(result.plan.items, CAUGHT)


@pytest.mark.parametrize("intensity", ["standard", "pro"])
def test_a_recorded_llm_skull_moment_survives_the_budgets(
    intensity: ProEditIntensity,
) -> None:
    llm = FakeLLMClient(RECORDED_SKULL, repeat_last=True)

    result = director_plan(skull_request(intensity), llm)

    assert result.fallback is None
    assert_whole_skull(result.plan.items, CAUGHT)
    punch = [n for n in result.notes if n.kind == "zoom_punch"]
    assert [n.action for n in punch] == ["dropped"]
    assert punch[0].reason


def test_an_llm_skull_moment_request_is_expanded_like_the_rule_directors() -> None:
    reply = {
        "rationale": "A skull moment on the caught moment.",
        "items": [],
        "moments": [{"move": "skull_moment", "t": 16.37, "reason": "caught"}],
    }
    llm = FakeLLMClient(json.dumps(reply), repeat_last=True)

    result = director_plan(skull_request("standard"), llm)

    assert result.fallback is None
    assert_whole_skull(result.plan.items, CAUGHT)


def test_an_llm_bass_drop_request_is_placed_whole() -> None:
    reply = {
        "rationale": "A bass drop after the first punchline.",
        "items": [],
        "moments": [{"move": "bass_drop", "t": 11.0, "reason": "drop on night"}],
    }
    llm = FakeLLMClient(json.dumps(reply), repeat_last=True)

    result = director_plan(skull_request("standard"), llm)

    assert result.fallback is None
    drops = [g for g in find_composites(result.plan.items) if g.move == "bass_drop"]
    assert len(drops) == 1
    kinds = {i.kind for i in result.plan.items if i.id in drops[0].ids}
    assert {"sfx", "audio_fx"} <= kinds


def test_an_llm_moment_past_the_clip_end_is_sent_back() -> None:
    bad = {
        "rationale": "Too late.",
        "items": [],
        "moments": [{"move": "skull_moment", "t": 99.0, "reason": "late"}],
    }
    llm = FakeLLMClient(json.dumps(bad), repeat_last=True)

    result = director_plan(skull_request("standard"), llm)

    assert result.fallback is not None
    assert any("past the clip end" in p for r in result.invalid_replies for p in r)
