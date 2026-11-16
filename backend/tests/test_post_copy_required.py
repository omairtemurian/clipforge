"""Tests for the always-included hashtags of the post copy (steering, owner
request 2026-11-02): the required hashtags are in every platform's post,
once (any letter case), first, and are never cut or dropped by a rewrite."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from builders import make_clip
from clipforge.models import CopyPlatform, PostCopy, PostCopyRequest
from clipforge.pipeline.step import TRANSCRIPT
from clipforge.post_copy import write_copy
from clipforge.post_copy_fit import STYLES, utf8_bytes, utf16_units
from clipforge.publishers.base import hashtag_line
from clipforge.required_tags import clean_tags, merge_tags, tags_from_text
from fakes import FIXTURES, FakeLLMClient

REPLIES: dict[str, dict[str, Any]] = json.loads(
    (FIXTURES / "post_copy" / "replies.json").read_text()
)
REQUIRED = ["MyBrand", "ad"]
NOW = PostCopy(title="Old", caption="Old description.", hashtags=["old", "tags"])


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
    required: list[str] | None = None,
    **fields: Any,
) -> PostCopy:
    request = PostCopyRequest(platform=platform, **fields)
    required = REQUIRED if required is None else required
    return write_copy(llm, request, make_clip("karaoke_bold"), work, "", required)


@pytest.mark.parametrize("platform", ["youtube", "tiktok", "instagram", "facebook"])
def test_every_platform_carries_the_required_hashtags_first(
    work: Path, platform: CopyPlatform
) -> None:
    llm = FakeLLMClient(json.dumps(REPLIES["first"]))

    copy = ask(work, llm, platform)

    assert copy.hashtags[:2] == REQUIRED
    assert "#MyBrand #ad" in hashtag_line(copy.hashtags)
    assert "#MyBrand, #ad" not in llm.calls[0][1]
    assert "#MyBrand #ad" in llm.calls[0][1]


def test_the_ais_own_copy_of_a_required_tag_is_dropped_in_any_case(
    work: Path,
) -> None:
    reply = {**REPLIES["first"], "hashtags": ["mybrand", "AD", "yoga", "#Ad"]}
    llm = FakeLLMClient(json.dumps(reply))

    copy = ask(work, llm, "tiktok")

    assert copy.hashtags == ["MyBrand", "ad", "yoga"]


def test_no_required_hashtags_changes_nothing(work: Path) -> None:
    llm = FakeLLMClient(json.dumps(REPLIES["first"]))

    copy = ask(work, llm, "youtube", required=[])

    assert copy.hashtags == ["yoga", "standup", "comedy", "FunnyMoments"]
    assert "added after your text" not in llm.calls[0][1]


def test_the_ais_tags_are_counted_without_the_required_ones(work: Path) -> None:
    many = {"hashtags": [f"tag{index}" for index in range(20)]}
    llm = FakeLLMClient(json.dumps(many))

    copy = ask(work, llm, "facebook", hashtags="more", current=NOW)

    assert copy.hashtags == [*REQUIRED, *[f"tag{index}" for index in range(7)]]
    assert "Hashtags: 4 to 7" in llm.calls[0][1]


def test_fewer_hashtags_keeps_the_required_ones(work: Path) -> None:
    llm = FakeLLMClient(json.dumps(REPLIES["fewer"]))

    copy = ask(work, llm, "tiktok", hashtags="fewer", current=NOW)

    assert copy.hashtags == ["MyBrand", "ad", "yoga"]


def test_none_hashtags_needs_no_llm_and_keeps_the_required_ones(work: Path) -> None:
    llm = FakeLLMClient()

    copy = ask(work, llm, "instagram", hashtags="none", current=NOW)

    assert copy.hashtags == REQUIRED
    assert (copy.title, copy.caption) == (NOW.title, NOW.caption)
    assert llm.calls == []


def test_a_tone_rewrite_without_hashtags_keeps_the_required_ones(work: Path) -> None:
    llm = FakeLLMClient(json.dumps(REPLIES["casual"]))

    copy = ask(work, llm, "youtube", tone="casual", hashtags="none", current=NOW)

    assert copy.hashtags == REQUIRED


def test_a_tone_rewrite_adds_the_required_ones_to_the_current_tags(
    work: Path,
) -> None:
    llm = FakeLLMClient(json.dumps(REPLIES["casual"]))
    current = NOW.model_copy(update={"hashtags": ["old", "AD"]})

    copy = ask(work, llm, "youtube", tone="casual", current=current)

    assert copy.hashtags == ["MyBrand", "ad", "old"]


def test_the_ais_tags_give_way_at_the_instagram_limit(work: Path) -> None:
    many = {**REPLIES["first"], "hashtags": [f"tag{index}" for index in range(40)]}
    llm = FakeLLMClient(json.dumps(many))
    required = [f"required{index}" for index in range(25)]

    copy = ask(work, llm, "instagram", required=required)

    assert len(copy.hashtags) == STYLES["instagram"].tags_max
    assert copy.hashtags[:25] == required


def test_youtube_cuts_the_ai_text_not_the_required_tags(work: Path) -> None:
    long = {**REPLIES["overlong"], "description": "wörd " * 1500}
    llm = FakeLLMClient(json.dumps(long))
    required = [f"campaigntag{index}" for index in range(25)]

    copy = ask(work, llm, "youtube", required=required)

    assert copy.hashtags[: len(required)] == required
    body = copy.caption + "\n\n" + hashtag_line(copy.hashtags)
    assert utf8_bytes(body) <= STYLES["youtube"].text_max
    assert copy.caption.endswith("…")


@pytest.mark.parametrize(
    ("platform", "measure"), [("tiktok", utf16_units), ("instagram", len)]
)
def test_a_platform_limit_shortens_the_text_and_keeps_the_required_tags(
    work: Path, platform: CopyPlatform, measure: Any
) -> None:
    llm = FakeLLMClient(json.dumps(REPLIES["overlong"]))
    required = [f"required{index}" for index in range(12)]

    copy = ask(work, llm, platform, required=required)

    whole = copy.caption + "\n\n" + hashtag_line(copy.hashtags)
    assert measure(whole) <= 2200
    assert copy.hashtags[:12] == required
    assert copy.caption.endswith("…")


def test_a_hashtag_rewrite_cuts_the_caption_for_the_required_tags(
    work: Path,
) -> None:
    full = NOW.model_copy(update={"caption": "word " * 440})
    llm = FakeLLMClient()

    copy = ask(work, llm, "instagram", hashtags="none", current=full)

    whole = copy.caption + "\n\n" + hashtag_line(copy.hashtags)
    assert len(whole) <= 2200 and copy.caption.endswith("…")
    assert copy.hashtags == REQUIRED


def test_clean_and_merge_tags() -> None:
    assert clean_tags(["#a b", "A", " ", "#", "c"]) == ["ab", "A", "c"]
    assert merge_tags(["x"], ["X", "y", "z"], 2) == ["x", "y"]
    assert merge_tags(["x", "y"], ["z"], 1) == ["x", "y"]
    assert merge_tags([], ["a", "A", "b"]) == ["a", "b"]


def test_tags_from_text_reads_json_or_separated_text() -> None:
    assert tags_from_text('["#a", "B", "b"]') == ["a", "B"]
    assert tags_from_text("#a, b  c") == ["a", "b", "c"]
    assert tags_from_text("") == []
