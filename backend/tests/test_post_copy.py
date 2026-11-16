"""Tests for the post copy generator (clipforge.post_copy): the text of a
post per platform from recorded LLM replies, each option of Rewrite with
AI, and the cutting of an over-long reply to the platform's limits."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from builders import make_clip
from clipforge.llm_http import LLMError
from clipforge.models import CopyPlatform, PostCopy, PostCopyRequest
from clipforge.pipeline.step import TRANSCRIPT, StepError
from clipforge.post_copy import PostCopyError, write_copy
from clipforge.post_copy_fit import STYLES, utf8_bytes, utf16_units
from clipforge.publishers.base import hashtag_line
from fakes import FIXTURES, FakeLLMClient

REPLIES: dict[str, dict[str, Any]] = json.loads(
    (FIXTURES / "post_copy" / "replies.json").read_text()
)
CREDIT = "Source: Standup Hour"
NOW = PostCopy(
    title="Old title",
    caption="Old description.",
    hashtags=["old", "tags", "here"],
)


def recorded(name: str) -> str:
    """Return the recorded reply name as the LLM sends it."""
    return json.dumps(REPLIES[name])


@pytest.fixture
def work(tmp_path: Path) -> Path:
    folder = tmp_path / "work"
    folder.mkdir()
    shutil.copy(FIXTURES / TRANSCRIPT, folder / TRANSCRIPT)
    return folder


def ask(
    work: Path,
    llm: FakeLLMClient,
    platform: CopyPlatform = "youtube",
    credit: str = "",
    **fields: Any,
) -> PostCopy:
    request = PostCopyRequest(platform=platform, **fields)
    return write_copy(llm, request, make_clip("karaoke_bold"), work, credit)


def test_first_copy_is_written_per_platform_style(work: Path) -> None:
    llm = FakeLLMClient(recorded("first"), repeat_last=True)

    youtube = ask(work, llm, "youtube")
    tiktok = ask(work, llm, "tiktok")

    assert youtube.title == "Why yoga asked me one question"
    assert youtube.caption.startswith("A comedian tries yoga")
    assert youtube.hashtags == ["yoga", "standup", "comedy", "FunnyMoments"]
    assert tiktok.title == ""
    assert tiktok.caption == (
        "Why yoga asked me one question\n\n"
        "A comedian tries yoga and the teacher asks one question that nobody "
        "can answer."
    )
    system, user = llm.calls[0]
    assert '"hashtags"' in system and '"description"' in system
    assert user.startswith("Platform: YouTube Shorts.")
    assert "Write: a title and a description and hashtags." in user
    assert "Hashtags: 3 to 5" in user
    assert "What is said in the clip:\nsaid, why are we on\n\n" in user
    assert "Hook: He ate it all" in user
    assert "at most 100 characters" in user and "5000 bytes" in user
    assert "Platform: TikTok." in llm.calls[1][1]
    assert "2200 UTF-16 units" in llm.calls[1][1]


def test_credit_line_closes_the_description(work: Path) -> None:
    llm = FakeLLMClient(recorded("first"))

    copy = ask(work, llm, "instagram", CREDIT)

    assert copy.caption.endswith("can answer.\n\n" + CREDIT)
    assert f"A credit line is added after the description: {CREDIT}" in llm.calls[0][1]


@pytest.mark.parametrize("tone", ["casual", "punchy", "professional", "funny"])
def test_each_tone_rewrites_only_the_text(work: Path, tone: str) -> None:
    llm = FakeLLMClient(recorded(tone))

    copy = ask(work, llm, "youtube", tone=tone, current=NOW)

    assert copy.title == REPLIES[tone]["title"]
    assert copy.caption == REPLIES[tone]["description"]
    assert copy.hashtags == NOW.hashtags
    system, user = llm.calls[0]
    assert "hashtags" not in system.split("JSON Schema")[1]
    assert f"Tone: {tone}" in user
    assert "Write: a title and a description." in user
    assert "Hashtags:" not in user
    assert "Current description: Old description." in user


@pytest.mark.parametrize("layout", ["short", "list", "story"])
def test_each_format_rewrites_only_the_text(work: Path, layout: str) -> None:
    llm = FakeLLMClient(recorded(layout))

    copy = ask(work, llm, "facebook", format=layout, current=NOW)

    assert copy.title == REPLIES[layout]["title"]
    assert copy.caption == REPLIES[layout]["description"]
    assert copy.hashtags == NOW.hashtags
    assert f"Format: {layout}" in llm.calls[0][1]


def test_tone_and_format_on_a_platform_without_titles(work: Path) -> None:
    llm = FakeLLMClient(recorded("list"))
    current = NOW.model_copy(update={"title": ""})

    copy = ask(work, llm, "tiktok", tone="punchy", format="list", current=current)

    assert copy.title == ""
    assert (
        copy.caption == "Three things about yoga\n\n" + REPLIES["list"]["description"]
    )
    assert "Tone: punchy" in llm.calls[0][1] and "Format: list" in llm.calls[0][1]


def test_more_hashtags_changes_only_the_hashtags(work: Path) -> None:
    llm = FakeLLMClient(recorded("more"))

    copy = ask(work, llm, "tiktok", hashtags="more", current=NOW)

    assert copy.hashtags == REPLIES["more"]["hashtags"][:8]
    assert (copy.title, copy.caption) == (NOW.title, NOW.caption)
    system, user = llm.calls[0]
    assert "Hashtags: 5 to 8" in user
    assert "Write: hashtags." in user
    assert '"Description"' not in system.split("JSON Schema")[1]


def test_fewer_hashtags_changes_only_the_hashtags(work: Path) -> None:
    llm = FakeLLMClient(recorded("fewer"))

    copy = ask(work, llm, "tiktok", hashtags="fewer", current=NOW)

    assert copy.hashtags == ["yoga"]
    assert (copy.title, copy.caption) == (NOW.title, NOW.caption)
    assert "Hashtags: 1 to 2" in llm.calls[0][1]


def test_more_hashtags_never_go_over_what_was_asked(work: Path) -> None:
    many = {"hashtags": [f"tag{index}" for index in range(20)]}
    llm = FakeLLMClient(json.dumps(many))

    copy = ask(work, llm, "facebook", hashtags="more", current=NOW)

    assert copy.hashtags == [f"tag{index}" for index in range(7)]


def test_no_hashtags_needs_no_llm(work: Path) -> None:
    llm = FakeLLMClient()

    copy = ask(work, llm, "instagram", hashtags="none", current=NOW)

    assert copy == NOW.model_copy(update={"hashtags": []})
    assert llm.calls == []


def test_a_new_tone_without_hashtags_keeps_them_gone(work: Path) -> None:
    llm = FakeLLMClient(recorded("casual"))

    copy = ask(work, llm, "youtube", tone="casual", hashtags="none", current=NOW)

    assert copy.hashtags == []
    assert copy.title == REPLIES["casual"]["title"]
    assert "Hashtags:" not in llm.calls[0][1]


def test_title_and_caption_are_cut_to_youtubes_limits(work: Path) -> None:
    long_description = "wörd " * 1500
    reply = {**REPLIES["overlong"], "description": long_description}
    llm = FakeLLMClient(json.dumps(reply))

    copy = ask(work, llm, "youtube")

    assert len(copy.title) <= 100 and copy.title.endswith("…")
    assert " " not in copy.title[-3:]
    body = copy.caption + "\n\n" + hashtag_line(copy.hashtags)
    assert utf8_bytes(body) <= STYLES["youtube"].text_max
    assert copy.caption.endswith("…") and "wörd" in copy.caption
    assert utf8_bytes(body) > 4900


@pytest.mark.parametrize(
    ("platform", "measure"), [("tiktok", utf16_units), ("instagram", len)]
)
def test_caption_is_cut_so_that_it_fits_with_the_hashtags(
    work: Path, platform: CopyPlatform, measure: Any
) -> None:
    llm = FakeLLMClient(recorded("overlong"))

    copy = ask(work, llm, platform, CREDIT)

    whole = copy.caption + "\n\n" + hashtag_line(copy.hashtags)
    assert measure(whole) <= 2200
    assert measure(whole) > 2100
    assert copy.caption.startswith("A very long title that goes on and on")
    assert copy.caption.endswith(CREDIT)
    assert "…\n\n" + CREDIT in copy.caption


def test_tiktok_counts_utf16_units_not_characters(work: Path) -> None:
    emoji = "🍕" * 1500
    llm = FakeLLMClient(json.dumps({**REPLIES["first"], "description": emoji}))

    copy = ask(work, llm, "tiktok")

    whole = copy.caption + "\n\n" + hashtag_line(copy.hashtags)
    assert utf16_units(whole) <= 2200
    assert len(whole) < 1200


def test_hashtag_rewrite_cuts_a_caption_that_no_longer_fits(work: Path) -> None:
    llm = FakeLLMClient(recorded("more"))
    full = NOW.model_copy(update={"caption": "word " * 440})

    copy = ask(work, llm, "instagram", hashtags="more", current=full)

    whole = copy.caption + "\n\n" + hashtag_line(copy.hashtags)
    assert len(whole) <= 2200 and copy.caption.endswith("…")


def test_an_invalid_reply_is_sent_back_with_its_errors(work: Path) -> None:
    llm = FakeLLMClient('{"title": ""}', recorded("first"))

    copy = ask(work, llm, "youtube")

    assert copy.title == REPLIES["first"]["title"]
    retry = llm.calls[1][1]
    assert "Your previous reply was not valid:" in retry
    assert "title: " in retry and "description: " in retry


def test_no_valid_reply_raises(work: Path) -> None:
    llm = FakeLLMClient("not json", repeat_last=True)

    with pytest.raises(PostCopyError, match="no valid YouTube Shorts text"):
        ask(work, llm)

    assert len(llm.calls) == 3


def test_llm_errors_and_a_missing_transcript_pass_through(
    work: Path, tmp_path: Path
) -> None:
    class Refusing:
        def complete_json(self, system: str, user: str) -> str:
            raise LLMError("refused")

    with pytest.raises(LLMError):
        ask(work, Refusing())  # type: ignore[arg-type]
    with pytest.raises(StepError):
        ask(tmp_path, FakeLLMClient(recorded("first")))


def test_a_rewrite_needs_the_current_text() -> None:
    with pytest.raises(ValueError, match="current is required"):
        PostCopyRequest(platform="youtube", tone="casual")
