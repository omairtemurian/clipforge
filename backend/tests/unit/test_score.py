"""Tests for the score formula (SPEC 6.6): weights, components and ranking."""

import math
import re

import pytest
from builders import event
from clipforge.models import (
    CandidateList,
    ContentGenre,
    ScoredCandidate,
    Scores,
)
from clipforge.pipeline.score import (
    LAUGH_AFTER_END_S,
    LAUGH_BEFORE_END_S,
    component_weights,
    energy_score,
    laugh_score,
    rank,
    score_candidate,
)
from clipforge.pipeline.step import StepError
from fakes import LLM_RESPONSE

SPEC_WEIGHTS = {"llm": 0.6, "laugh": 0.25, "energy": 0.15}
# A 10-30 s candidate with the LLM scores of the SPEC example: an average of 65.
CANDIDATE = (
    CandidateList.model_validate_json(LLM_RESPONSE.read_bytes())
    .clips[0]
    .model_copy(
        update={
            "start": 10.0,
            "end": 30.0,
            "hook": 80,
            "flow": 70,
            "value": 60,
            "trend": 50,
        }
    )
)
# A laugh of 0.8 right after the end, and an energy peak over half the clip.
EVENTS = [event("laugh", 30.5, 31.5, 0.8), event("energy_peak", 12.0, 22.0)]
# A clip end whose laugh window starts at 32.2 - 3 = 29.200000000000003.
END = 32.2


def scored(title: str, overall: int) -> ScoredCandidate:
    """Return CANDIDATE with this title and overall score."""
    scores = Scores(
        overall=overall, hook=80, flow=70, value=60, trend=50, laugh=0.0, energy=0.0
    )
    candidate = CANDIDATE.model_copy(update={"title": title})
    return ScoredCandidate(**candidate.model_dump(), scores=scores)


def test_comedy_overall_is_99_times_the_weighted_components() -> None:
    weights = component_weights("comedy", SPEC_WEIGHTS)

    result = score_candidate(CANDIDATE, EVENTS, weights)

    assert weights == SPEC_WEIGHTS
    assert result.scores == Scores(
        overall=66, hook=80, flow=70, value=60, trend=50, laugh=0.8, energy=0.5
    )
    assert result.scores.overall == round(
        99 * (0.6 * 65 / 99 + 0.25 * 0.8 + 0.15 * 0.5)
    )
    assert result.model_dump(exclude={"scores"}) == CANDIDATE.model_dump()


@pytest.mark.parametrize("genre", ["podcast", "talk", "interview"])
def test_other_genres_give_laughs_no_weight_and_scale_the_rest_up(
    genre: ContentGenre,
) -> None:
    weights = component_weights(genre, SPEC_WEIGHTS)

    result = score_candidate(CANDIDATE, EVENTS, weights)

    assert weights == pytest.approx({"llm": 0.8, "laugh": 0.0, "energy": 0.2})
    assert weights["laugh"] == 0.0
    assert result.scores.overall == round(99 * (0.8 * 65 / 99 + 0.2 * 0.5)) == 62
    # The laugh is still measured, though it does not count.
    assert (result.scores.laugh, result.scores.energy) == (0.8, 0.5)


@pytest.mark.parametrize(
    ("genre", "configured", "expected"),
    [
        ("comedy", {"llm": 3, "laugh": 1, "energy": 1}, (0.6, 0.2, 0.2)),
        ("comedy", {"llm": 1.0}, (1.0, 0.0, 0.0)),
        ("comedy", {"llm": 0.0, "laugh": 2.0, "energy": 2.0}, (0.0, 0.5, 0.5)),
        ("podcast", {"llm": 1.0, "laugh": 5.0}, (1.0, 0.0, 0.0)),
        ("talk", {"llm": 0.3, "laugh": 0.4, "energy": 0.3}, (0.5, 0.0, 0.5)),
    ],
)
def test_weights_are_scaled_to_sum_to_1(
    genre: ContentGenre,
    configured: dict[str, float],
    expected: tuple[float, float, float],
) -> None:
    weights = component_weights(genre, configured)

    assert list(weights) == ["llm", "laugh", "energy"]
    assert tuple(weights.values()) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("genre", "configured", "message"),
    [
        (
            "comedy",
            {"llm": 0.6, "views": 0.4},
            "score_weights has unknown components: views; use llm, laugh, energy",
        ),
        ("comedy", {"llm": 0.6, "laugh": -0.25}, "numbers >= 0, not laugh -0.25"),
        ("comedy", {"llm": math.nan}, "numbers >= 0, not llm nan"),
        ("comedy", {"llm": math.inf}, "numbers >= 0, not llm inf"),
        (
            "comedy",
            {"llm": 0.0, "laugh": 0.0, "energy": 0.0},
            "no weight to llm, laugh, energy, the components of comedy clips",
        ),
        ("comedy", {}, "no weight to llm, laugh, energy"),
        (
            "podcast",
            {"laugh": 1.0},
            "no weight to llm, energy, the components of podcast clips",
        ),
    ],
)
def test_weights_that_cannot_weigh_clips_are_an_error(
    genre: ContentGenre, configured: dict[str, float], message: str
) -> None:
    with pytest.raises(StepError, match=re.escape(message)):
        component_weights(genre, configured)


@pytest.mark.parametrize(
    ("start", "end", "counted"),
    [
        (28.0, 29.2, True),  # ends where the window starts, END - 3 s
        (28.0, 29.199, False),
        (34.2, 35.0, True),  # starts where the window ends, END + 2 s
        (34.201, 35.0, False),
        (31.0, 33.0, True),
        (20.0, 40.0, True),  # a long laugh over the whole window
        (10.0, 12.0, False),
    ],
)
def test_laughs_count_from_3s_before_the_end_to_2s_after(
    start: float, end: float, counted: bool
) -> None:
    assert (LAUGH_BEFORE_END_S, LAUGH_AFTER_END_S) == (3.0, 2.0)
    assert END - LAUGH_BEFORE_END_S != 29.2  # float noise at the boundary

    laugh = laugh_score(END, [event("laugh", start, end, 0.7)])

    assert laugh == (0.7 if counted else 0.0)


def test_the_laugh_score_is_the_loudest_laugh_in_the_window() -> None:
    events = [
        event("laugh", 30.0, 31.0, 0.3),
        event("laugh", 33.0, 34.0, 0.9),
        event("laugh", 10.0, 11.0, 1.0),
        event("applause", 32.0, 33.0, 1.0),
        event("energy_peak", 31.0, 33.0, 1.0),
    ]

    assert laugh_score(END, events) == 0.9
    assert laugh_score(END, events[2:]) == 0.0
    assert laugh_score(END, []) == 0.0


@pytest.mark.parametrize(
    ("peaks", "expected"),
    [
        ([], 0.0),
        ([(12.0, 17.0)], 0.25),
        ([(12.0, 16.0), (14.0, 18.0)], 0.3),  # overlapping peaks count once
        ([(11.0, 19.0), (12.0, 13.0)], 0.4),  # a peak within another
        ([(28.0, 35.0), (5.0, 12.0)], 0.2),  # only the parts within the clip
        ([(0.0, 40.0)], 1.0),
        ([(0.0, 10.0), (30.0, 31.0)], 0.0),  # touching the clip's ends
        ([(10.0, 10.0 + 20 / 3)], 0.333),
    ],
)
def test_energy_is_the_fraction_of_the_clip_that_peaks_cover(
    peaks: list[tuple[float, float]], expected: float
) -> None:
    events = [event("energy_peak", start, end) for start, end in peaks]

    assert energy_score(10.0, 30.0, events) == expected


def test_energy_counts_only_energy_peaks_of_a_clip_with_a_length() -> None:
    assert energy_score(10.0, 30.0, [event("laugh", 10.0, 30.0)]) == 0.0
    assert energy_score(30.0, 30.0, [event("energy_peak", 0.0, 40.0)]) == 0.0


def test_rank_keeps_the_best_overall_scores_best_first() -> None:
    low, high, middle = scored("low", 40), scored("high", 90), scored("middle", 60)

    assert rank([low, high, middle], 10) == [high, middle, low]
    assert rank([low, high, middle], 2) == [high, middle]
    assert rank([], 3) == []


def test_rank_keeps_the_order_of_equal_overall_scores() -> None:
    first, second = scored("first", 70), scored("second", 70)

    assert rank([first, second], 2) == [first, second]
    assert rank([second, first], 2) == [second, first]
    assert rank([second, first, scored("best", 71)], 2)[1] == second
