"""Tests for a post's payload built from its text on each platform
(clipforge.post_payload): defaults from the clip, link and hashtags,
collaborators and privacy where the API takes them, and platform limits."""

import pytest
from builders import make_clip
from clipforge.models import Clip, PostText
from clipforge.post_payload import (
    TEXT_KEY,
    PayloadInvalid,
    build_payload,
    ready_problem,
    text_of,
)


@pytest.fixture
def clip() -> Clip:
    return make_clip("karaoke_bold", title="Pizza night", description="Credit: @chef")


def test_youtube_payload_takes_the_clips_text_where_none_is_given(clip: Clip) -> None:
    payload = build_payload("youtube", PostText(), clip)

    assert payload["title"] == "Pizza night"
    assert payload["description"] == "Credit: @chef\n\n#food #pizza #funny"
    assert payload["tags"] == ["food", "pizza", "funny"]
    assert "privacy" not in payload
    assert text_of(payload) == PostText()


def test_youtube_payload_puts_link_and_hashtags_after_the_text(clip: Clip) -> None:
    text = PostText(
        title="Best bite",
        caption="Watch it all",
        hashtags=["#shorts"],
        link="https://youtu.be/full",
        privacy="unlisted",
        options={"made_for_kids": False, "category_id": "24"},
    )

    payload = build_payload("youtube", text, clip)

    assert payload["description"] == "Watch it all\n\nhttps://youtu.be/full\n\n#shorts"
    assert (payload["title"], payload["tags"], payload["privacy"]) == (
        "Best bite",
        ["shorts"],
        "unlisted",
    )
    assert payload["category_id"] == "24"
    assert text_of(payload) == text
    assert payload[TEXT_KEY]["link"] == "https://youtu.be/full"


def test_title_less_platforms_carry_the_title_in_the_caption(clip: Clip) -> None:
    tiktok = build_payload("tiktok", PostText(privacy="SELF_ONLY", hashtags=[]), clip)
    instagram = build_payload(
        "instagram", PostText(title="", collaborators=["@chef.k"]), clip
    )

    assert tiktok["caption"] == "Pizza night\n\nCredit: @chef"
    assert tiktok["privacy_level"] == "SELF_ONLY"
    assert instagram["caption"] == "Credit: @chef\n\n#food #pizza #funny"
    assert instagram["collaborators"] == ["chef.k"]


def test_facebook_payload_has_a_title_and_page_collaborators(clip: Clip) -> None:
    payload = build_payload(
        "facebook", PostText(collaborators=["1234567890"], privacy="public"), clip
    )

    assert (payload["title"], payload["collaborator_page_ids"]) == (
        "Pizza night",
        ["1234567890"],
    )


@pytest.mark.parametrize(
    ("platform", "text", "problem"),
    [
        ("youtube", PostText(collaborators=["someone"]), "no collaborator tags"),
        ("tiktok", PostText(collaborators=["someone"]), "no collaborator tags"),
        ("instagram", PostText(privacy="private"), "always public"),
        ("youtube", PostText(privacy="friends"), "privacy"),
        ("youtube", PostText(title="x" * 101), "title"),
        ("youtube", PostText(title=""), "needs a title"),
        ("youtube", PostText(caption="a <b>"), '"<" or ">"'),
        ("youtube", PostText(caption="é" * 2501), "5000 bytes"),
        ("youtube", PostText(hashtags=[f"tag{n:03}" for n in range(80)]), "500"),
        ("tiktok", PostText(caption="😀" * 1101), "2200"),
        ("instagram", PostText(hashtags=[f"t{n}" for n in range(31)]), "30 hashtags"),
        ("facebook", PostText(collaborators=["not-a-page"]), "Facebook Page id"),
        ("youtube", PostText(options={"title": "sneaky"}), "no option title"),
        ("youtube", PostText(options={"allow_duet": True}), "no option allow_duet"),
        ("x", PostText(), "cannot post to x yet"),
    ],
)
def test_payloads_over_a_platform_limit_are_refused(
    clip: Clip, platform: str, text: PostText, problem: str
) -> None:
    with pytest.raises(PayloadInvalid) as caught:
        build_payload(platform, text, clip)  # type: ignore[arg-type]

    assert problem in caught.value.message


def test_tiktok_caption_counts_utf16_units(clip: Clip) -> None:
    fits = PostText(title="", caption="😀" * 1100, hashtags=[])

    assert len(build_payload("tiktok", fits, clip)["caption"]) == 1100


def test_link_must_be_a_web_url() -> None:
    with pytest.raises(ValueError, match="http"):
        PostText(link="ftp://example.com/video")

    assert PostText(link="  ").link is None


def test_tiktok_needs_a_privacy_before_publishing(clip: Clip) -> None:
    draft = build_payload("tiktok", PostText(), clip)
    chosen = build_payload("tiktok", PostText(privacy="PUBLIC_TO_EVERYONE"), clip)

    assert ready_problem("tiktok", draft) is not None
    assert ready_problem("tiktok", chosen) is None
    assert ready_problem("youtube", build_payload("youtube", PostText(), clip)) is None
