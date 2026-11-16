"""Tests for the SPEC 5 timing and length-preset rules of validate_candidate."""

import pytest
from clipforge.candidate_rules import length_range, longest_clip, validate_candidate
from clipforge.config import Settings
from clipforge.models import ClipCandidate, LengthPreset

CFG = Settings(clip_min_s=20, clip_max_s=75)
PAYLOAD = {
    "title": "Airport bit",
    "hook_text": "Wait for it",
    "description": "A bit about airports.",
    "hashtags": ["comedy", "standup", "travel"],
    "emphasis_words": [],
    "reason": "Setup and punchline.",
    "hook": 50,
    "flow": 50,
    "value": 50,
    "trend": 50,
}
# Clip length in seconds -> whether the preset keeps it.
PRESET_CASES: dict[LengthPreset, dict[float, bool]] = {
    "lt30": {29.9: True, 30.0: False},
    "30_60": {29.9: False, 30.0: True, 60.0: True, 60.1: False},
    "60_90": {59.9: False, 60.0: True, 90.0: True, 90.1: False},
    "90_180": {89.9: False, 90.0: True, 180.0: True, 180.1: False},
    "180_300": {179.9: False, 180.0: True, 300.0: True, 300.1: False},
    "300_600": {299.9: False, 300.0: True, 600.0: True, 600.1: False},
    "600_900": {599.9: False, 600.0: True, 900.0: True, 900.1: False},
    "auto": {19.9: False, 20.0: True, 75.1: True, 180.0: True, 180.1: False},
}


def timed(start: float, end: float) -> ClipCandidate:
    """Build a valid candidate spanning [start, end] seconds."""
    return ClipCandidate.model_validate(PAYLOAD | {"start": start, "end": end})


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (0.0, 60.0, (True, "")),
        # 42.3 - 12.3 is 29.999999999999996 in floating point.
        (12.3, 42.3, (True, "")),
        (-0.5, 30.0, (False, "start -0.5s is negative")),
        (40.0, 40.0, (False, "start 40s is not before end 40s")),
        (50.0, 40.0, (False, "start 50s is not before end 40s")),
        (30.0, 60.5, (False, "end 60.5s is after the video duration 60s")),
    ],
)
def test_validate_candidate_checks_timing(
    start: float, end: float, expected: tuple[bool, str]
) -> None:
    assert validate_candidate(timed(start, end), 60.0, ["30_60"], CFG) == expected


@pytest.mark.parametrize(
    ("preset", "length", "kept"),
    [
        (preset, length, kept)
        for preset, cases in PRESET_CASES.items()
        for length, kept in cases.items()
    ],
)
def test_validate_candidate_applies_length_preset(
    preset: LengthPreset, length: float, kept: bool
) -> None:
    clip = timed(100.0, 100.0 + length)
    ok, reason = validate_candidate(clip, 1200.0, [preset], CFG)
    assert ok is kept
    if kept:
        assert reason == ""
    else:
        assert reason.startswith(f"length {length:g}s is outside the chosen ranges")


def test_auto_preset_starts_at_the_configured_minimum() -> None:
    cfg = Settings(clip_min_s=10, clip_max_s=15)
    assert validate_candidate(timed(0.0, 12.0), 600.0, ["auto"], cfg) == (True, "")
    assert validate_candidate(timed(0.0, 9.0), 600.0, ["auto"], cfg) == (
        False,
        "length 9s is outside the chosen ranges: auto (10-180s)",
    )


def test_lt30_reason_names_the_exclusive_limit() -> None:
    assert validate_candidate(timed(0.0, 30.0), 60.0, ["lt30"], CFG) == (
        False,
        "length 30s is outside the chosen ranges: lt30 (under 30s)",
    )


@pytest.mark.parametrize(
    ("length", "kept"),
    [(20.0, True), (45.0, False), (75.0, True), (100.0, False), (240.0, True)],
)
def test_a_candidate_fits_any_of_several_presets(length: float, kept: bool) -> None:
    presets: list[LengthPreset] = ["lt30", "60_90", "180_300"]
    ok, reason = validate_candidate(timed(0.0, length), 600.0, presets, CFG)
    assert ok is kept
    if not kept:
        assert reason == (
            f"length {length:g}s is outside the chosen ranges: lt30 (under 30s), "
            "60_90 (60-90s), 180_300 (180-300s)"
        )


def test_longest_clip_is_the_longest_chosen_range() -> None:
    assert longest_clip(["auto"], CFG) == 180.0
    assert longest_clip(["lt30", "300_600"], CFG) == 600.0


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("lt30", (0.0, 30.0)),
        ("30_60", (30.0, 60.0)),
        ("60_90", (60.0, 90.0)),
        ("90_180", (90.0, 180.0)),
        ("180_300", (180.0, 300.0)),
        ("300_600", (300.0, 600.0)),
        ("600_900", (600.0, 900.0)),
        ("auto", (20.0, 180.0)),
    ],
)
def test_length_range_per_preset(
    preset: LengthPreset, expected: tuple[float, float]
) -> None:
    assert length_range(preset, CFG) == expected
