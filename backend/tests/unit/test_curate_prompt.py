"""Tests for the text of curate's LLM requests (SPEC 6.4, 6.5)."""

import json
import re
from pathlib import Path

import pytest
from clipforge.config import Settings
from clipforge.models import (
    CandidateList,
    ClipCandidate,
    LengthPreset,
    ProcessingSettings,
)
from clipforge.pipeline.curate_prompt import (
    MAX_ERRORS,
    describe_errors,
    system_prompt,
    user_prompt,
)
from clipforge.pipeline.enrich import PromptLine
from pydantic import ValidationError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CFG = Settings(clip_min_s=20, clip_max_s=75)
REPLY = json.loads((FIXTURES / "llm_response.json").read_text())


def errors_of(reply: str) -> str:
    """Return describe_errors for a reply that CandidateList rejects."""
    with pytest.raises(ValidationError) as excinfo:
        CandidateList.model_validate_json(reply)
    return describe_errors(excinfo.value)


def test_system_prompt_embeds_the_clip_candidate_json_schema() -> None:
    prompt = system_prompt("podcast", ProcessingSettings(), CFG)
    schema = json.dumps(ClipCandidate.model_json_schema(), indent=2)
    assert schema in prompt
    assert '{"clips": [...]}' in prompt
    assert re.search(r"\$\{?[A-Za-z_]", prompt) is None, "unfilled placeholder"


@pytest.mark.parametrize(
    ("presets", "cfg", "rule"),
    [
        (["auto"], CFG, "20 to 180 seconds (most often 20 to 75 seconds)"),
        (
            ["auto"],
            Settings(clip_min_s=15, clip_max_s=45),
            "15 to 180 seconds (most often 15 to 45 seconds)",
        ),
        (["lt30"], CFG, "under 30 seconds"),
        (["30_60"], CFG, "30 to 60 seconds"),
        (["90_180"], CFG, "90 to 180 seconds"),
        (["600_900"], CFG, "600 to 900 seconds"),
        (["lt30", "60_90"], CFG, "under 30 seconds or 60 to 90 seconds"),
    ],
)
def test_system_prompt_gives_the_clip_length_ranges(
    presets: list[LengthPreset], cfg: Settings, rule: str
) -> None:
    processing = ProcessingSettings(length_presets=presets)
    prompt = system_prompt("podcast", processing, cfg)
    assert f"short vertical clips of {rule} for" in prompt
    assert f"end minus start must be {rule};" in prompt


def test_system_prompt_passes_on_the_keyword_prompt() -> None:
    processing = ProcessingSettings(keyword_prompt="  money\n  advice ")
    prompt = system_prompt("talk", processing, CFG)
    assert "The user is looking for: money advice\n" in prompt


@pytest.mark.parametrize("keyword_prompt", [None, "", " \n "])
def test_system_prompt_without_a_keyword_prompt_has_no_request_section(
    keyword_prompt: str | None,
) -> None:
    processing = ProcessingSettings(keyword_prompt=keyword_prompt)
    prompt = system_prompt("comedy", processing, CFG)
    assert "user's request" not in prompt
    assert "\n\n\n" not in prompt


def test_user_prompt_is_the_window_lines() -> None:
    lines = [PromptLine(0.5, "[00:00.5-00:01.4] S0: Hi."), PromptLine(2, "[b]")]
    assert user_prompt(lines) == "[00:00.5-00:01.4] S0: Hi.\n[b]"


def test_retry_user_prompt_adds_the_errors_after_the_lines() -> None:
    lines = [PromptLine(0.5, "[00:00.5-00:01.4] S0: Hi.")]
    prompt = user_prompt(lines, "- reply: Invalid JSON")
    assert prompt.startswith("[00:00.5-00:01.4] S0: Hi.\n\n")
    assert "was not valid:\n- reply: Invalid JSON\n" in prompt
    assert prompt.endswith(
        'Reply again with only the JSON object {"clips": [...]} '
        "described in the instructions."
    )


def test_describe_errors_names_the_reply_when_it_is_not_json() -> None:
    errors = errors_of("Sure! Here are the clips.")
    assert errors == "- reply: Invalid JSON: expected value at line 1 column 1"


def test_describe_errors_gives_the_path_of_each_bad_value() -> None:
    reply = json.loads(json.dumps(REPLY))
    reply["clips"][0]["title"] = "SECRET " * 11
    reply["clips"][2]["hook"] = 120
    errors = errors_of(json.dumps(reply)).splitlines()
    assert errors == [
        "- clips.0.title: String should have at most 70 characters",
        "- clips.2.hook: Input should be less than or equal to 99",
    ]


def test_describe_errors_does_not_repeat_the_bad_values() -> None:
    reply = json.loads(json.dumps(REPLY))
    reply["clips"][0]["title"] = "SECRET " * 11
    assert "SECRET" not in errors_of(json.dumps(reply))


def test_describe_errors_lists_at_most_max_errors() -> None:
    clips = [dict(REPLY["clips"][0], title="x" * 71) for _ in range(MAX_ERRORS + 5)]
    errors = errors_of(json.dumps({"clips": clips})).splitlines()
    assert len(errors) == MAX_ERRORS + 1
    assert errors[-1] == "- ... and 5 more errors"
