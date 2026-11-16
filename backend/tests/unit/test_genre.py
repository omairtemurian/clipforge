"""Tests for the genre a job follows and the genre prompts of curate (SPEC 6.5).

"auto" is comedy above one laugh event per minute of the timeframe, else
podcast; each genre has its rules in prompts/curate_<genre>.md.
"""

import logging
import re
from collections.abc import Sequence
from pathlib import Path
from typing import get_args

import pytest
from builders import event, source_meta
from clipforge.config import Settings
from clipforge.models import (
    ContentGenre,
    Genre,
    ProcessingSettings,
    SignalEvent,
    SignalList,
)
from clipforge.pipeline import curate
from clipforge.pipeline.curate_prompt import genre_prompt, system_prompt
from clipforge.pipeline.genre import auto_genre, job_genre
from clipforge.pipeline.step import (
    ENRICHED,
    META,
    SIGNALS,
    StepError,
    StepSettings,
    write_json,
)
from fakes import FakeLLMClient

CFG = Settings(clip_min_s=20, clip_max_s=75)
GENRES: tuple[ContentGenre, ...] = get_args(ContentGenre)
COMEDY_RULES = (
    "Every clip follows setup -> punchline -> laugh",
    "Start at the start of a sentence before the setup",
    "End after the laugh marker",
)
SPOKEN_RULES = ("Strong first sentence hook", "One complete idea", "A satisfying end")
REPLY_ONLY = 'Reply with only a JSON object of the form {"clips": [...]}: no other text'
LINE = "[00:01.5-00:02.9] S0: So, I tried yoga. [LAUGH 2.0s 0.80]"


def laughs(*starts: float) -> list[SignalEvent]:
    """Return a laugh of 2 s at each of starts."""
    return [event("laugh", start, start + 2, 0.8) for start in starts]


@pytest.mark.parametrize(
    ("starts", "seconds", "genre"),
    [
        ((10, 40), 60, "comedy"),
        ((10, 50, 70), 120, "comedy"),
        ((), 60, "podcast"),
        # Exactly one laugh per minute is not more than one.
        ((10,), 60, "podcast"),
        ((10, 70, 130), 180, "podcast"),
        ((10, 50, 70), 300, "podcast"),
    ],
)
def test_auto_is_comedy_above_one_laugh_per_minute(
    starts: Sequence[float], seconds: float, genre: ContentGenre
) -> None:
    assert auto_genre(laughs(*starts), 0, seconds) == genre


def test_auto_counts_only_the_laughs_that_start_in_the_timeframe() -> None:
    applause = [event("applause", 40, 45), event("applause", 60, 65)]
    outside = [*laughs(5, 29.9, 90), *applause]
    assert auto_genre(outside, 30, 90) == "podcast"
    assert auto_genre([*outside, *laughs(30, 89.9)], 30, 90) == "comedy"


def test_auto_logs_how_it_chose(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="clipforge.pipeline.genre"):
        auto_genre(laughs(10, 20, 30), 0, 90)
    assert (
        "genre auto: 3 laugh events in 0.0s-90.0s (2.00 per minute) -> comedy"
        in caplog.text
    )


@pytest.mark.parametrize("genre", GENRES)
def test_a_chosen_genre_is_kept_without_reading_signals(
    tmp_path: Path, genre: ContentGenre
) -> None:
    assert not (tmp_path / SIGNALS).exists()
    assert job_genre(tmp_path, ProcessingSettings(genre=genre), source_meta()) == genre


def test_auto_reads_the_laughs_from_signals_json(tmp_path: Path) -> None:
    write_json(tmp_path / SIGNALS, SignalList(laughs(10, 40)))
    auto = ProcessingSettings()
    assert job_genre(tmp_path, auto, source_meta(end=60)) == "comedy"
    assert job_genre(tmp_path, auto, source_meta(end=120)) == "podcast"


def test_auto_needs_the_signals_step(tmp_path: Path) -> None:
    with pytest.raises(StepError, match="not found; run the signals step first"):
        job_genre(tmp_path, ProcessingSettings(), source_meta())


@pytest.mark.parametrize("genre", GENRES)
def test_every_genre_prompt_has_the_length_keyword_and_reply_format(
    genre: ContentGenre,
) -> None:
    assert genre_prompt(genre).is_file()
    prompt = system_prompt(genre, ProcessingSettings(keyword_prompt="dogs"), CFG)
    rule = "20 to 180 seconds (most often 20 to 75 seconds)"
    assert f"short vertical clips of {rule} for" in prompt
    assert f"end minus start must be {rule};" in prompt
    assert "The user is looking for: dogs\n" in prompt
    assert REPLY_ONLY in prompt
    assert re.search(r"\$\{?[A-Za-z_]", prompt) is None, "unfilled placeholder"


def test_the_comedy_prompt_asks_for_setup_punchline_laugh() -> None:
    prompt = system_prompt("comedy", ProcessingSettings(), CFG)
    assert [rule for rule in COMEDY_RULES if rule not in prompt] == []
    assert [rule for rule in SPOKEN_RULES if rule in prompt] == []
    assert "stand-up comedy" in prompt


@pytest.mark.parametrize(
    ("genre", "video"),
    [
        ("podcast", "The video is a podcast"),
        ("talk", "The video is a talk"),
        ("interview", "The video is an interview"),
    ],
)
def test_the_other_prompts_ask_for_a_hook_one_idea_and_an_end(
    genre: ContentGenre, video: str
) -> None:
    prompt = system_prompt(genre, ProcessingSettings(), CFG)
    assert [rule for rule in SPOKEN_RULES if rule not in prompt] == []
    assert [rule for rule in COMEDY_RULES if rule in prompt] == []
    assert video in prompt


@pytest.mark.parametrize(
    ("genre", "video", "rule"),
    [
        ("sports_commentary", "The video is sports commentary", "The peak of"),
        ("faith", "The video is a sermon", "One message from start to end"),
        ("news", "The video is news", "Keep it accurate"),
        ("vlog", "The video is a vlog", "A small story with a turn"),
        ("gaming", "The video is gaming", "The big moment"),
        ("other", "does not fit one of the usual kinds", "stands on its own"),
    ],
)
def test_the_new_genres_have_their_own_rules(
    genre: ContentGenre, video: str, rule: str
) -> None:
    prompt = system_prompt(genre, ProcessingSettings(), CFG)
    assert video in prompt
    assert rule in prompt
    assert [rule for rule in COMEDY_RULES if rule in prompt] == []


def test_each_genre_has_its_own_prompt() -> None:
    prompts = {system_prompt(genre, ProcessingSettings(), CFG) for genre in GENRES}
    assert len(prompts) == len(GENRES)


@pytest.mark.parametrize(
    ("events", "chosen", "used"),
    [
        (laughs(2.9, 30), "auto", "comedy"),
        ([], "auto", "podcast"),
        (laughs(2.9, 30), "talk", "talk"),
        ([], "interview", "interview"),
    ],
)
def test_curate_asks_with_the_prompt_of_the_job_genre(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
    events: list[SignalEvent],
    chosen: Genre,
    used: ContentGenre,
) -> None:
    write_json(tmp_path / META, source_meta())
    write_json(tmp_path / SIGNALS, SignalList(events))
    (tmp_path / ENRICHED).write_text(f"{LINE}\n", encoding="utf-8")
    fake = FakeLLMClient()
    processing = ProcessingSettings(genre=chosen)
    step = StepSettings(source="unused", processing=processing, cfg=CFG, llm=fake)
    with caplog.at_level(logging.INFO, logger="clipforge.pipeline.curate"):
        curate.run(tmp_path, step)
    [(system, user)] = fake.calls
    assert system == system_prompt(used, processing, CFG)
    assert user == LINE
    assert f"asking for {used} clips (genre {chosen})" in caplog.text
