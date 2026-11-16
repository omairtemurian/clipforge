"""Tests for an Instagram reel's settings (clipforge.models.InstagramPostOptions,
clipforge.publishers.instagram_post) and the Meta Graph helpers
(clipforge.publishers.meta_graph): pure helpers, no network."""

from pathlib import Path

import httpx
import pytest
from builders import make_clip
from clipforge.models import InstagramPostOptions, instagram_caption_problem
from clipforge.oauth_tokens import Token
from clipforge.publishers.base import PublishError
from clipforge.publishers.instagram import SCOPES, instagram_client
from clipforge.publishers.instagram_api import instagram_accounts
from clipforge.publishers.instagram_post import (
    check_video,
    container_body,
    options_of,
    publishing_limit,
    status_failure,
)
from clipforge.publishers.meta_graph import AUTHORIZE_URL, exchange_grant, graph_error
from instagram_publish_fakes import APP_ID, CONFIG_ID, meta_settings, recorded
from pydantic import ValidationError

CLIP = make_clip("karaoke_bold", segments=[(10.0, 40.0)], title="Big moment")


def test_options_clean_collaborators_and_ignore_other_platform_keys() -> None:
    options = InstagramPostOptions.model_validate(
        {"collaborators": [" @friend.one "], "privacy_level": "SELF_ONLY"}
    )
    assert options.collaborators == ["friend.one"]
    assert options.share_to_feed is True


@pytest.mark.parametrize(
    "payload",
    [
        {"collaborators": ["not a name"]},
        {"collaborators": ["a", "b", "c", "d"]},
        {"thumb_offset_ms": -1},
        {"trial_strategy": "SOMETIMES"},
        {"caption": "x" * 2201},
    ],
)
def test_options_refuse_what_instagram_refuses(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InstagramPostOptions.model_validate(payload)
    with pytest.raises(PublishError, match="settings are invalid"):
        options_of(payload)


def test_caption_problems_count_hashtags_and_tags() -> None:
    assert instagram_caption_problem("#a " * 30) is None
    assert "30 hashtags" in str(instagram_caption_problem("#a " * 31))
    assert "20 @ tags" in str(instagram_caption_problem("@a " * 21))
    assert instagram_caption_problem("mail@example.com " * 25) is None


def test_the_container_takes_the_clip_caption_by_default() -> None:
    clip = CLIP.model_copy(update={"hashtags": ["habits", "#focus"]})
    body = container_body(InstagramPostOptions(), clip)
    assert body["caption"] == "Big moment\n\n#habits #focus"
    assert "thumb_offset" not in body and "trial_params" not in body


def test_check_video_takes_mp4_and_mov_only(tmp_path: Path) -> None:
    video = tmp_path / "clip.mov"
    video.write_bytes(b"1234")
    assert check_video(video, CLIP) == 4
    webm = tmp_path / "clip.webm"
    webm.write_bytes(b"1234")
    with pytest.raises(PublishError, match="MP4 or MOV"):
        check_video(webm, CLIP)
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(PublishError, match="empty"):
        check_video(empty, CLIP)


def test_status_failures_name_the_error_subcode() -> None:
    final = status_failure("ERROR", "Error: 2207050")
    assert (final.retryable, "restricted" in final.message) == (False, True)
    passing = status_failure("ERROR", "Error: 2207001")
    assert passing.retryable is True
    unknown = status_failure("ERROR", "")
    assert (unknown.retryable, "no reason given" in unknown.message) == (False, True)
    assert status_failure("EXPIRED", "").retryable is True


def test_publishing_limit_reads_usage_and_total() -> None:
    assert publishing_limit(recorded("publishing_limit")) == (4, 100)
    assert publishing_limit({"data": []}) is None
    assert publishing_limit({"data": [{"quota_usage": 1}]}) is None


def test_instagram_accounts_skip_pages_without_one_and_sort() -> None:
    accounts = instagram_accounts(recorded("pages"))
    assert [a["username"] for a in accounts] == ["cliplab", "cliplab.shorts"]
    assert instagram_accounts({"data": "nope"}) == []


@pytest.mark.parametrize(
    ("status", "error", "retryable", "text"),
    [
        (400, {"code": 190, "message": "expired"}, False, "connect the account"),
        (400, {"code": 200, "message": "no"}, False, "permission is missing"),
        (400, {"code": 17, "message": "slow down"}, True, "code 17"),
        (400, {"code": 9, "error_subcode": 2207042}, False, "code 9/2207042"),
        (400, {"code": 100, "is_transient": True}, True, "HTTP 400"),
        (503, {}, True, "no reason given"),
    ],
)
def test_graph_errors_are_final_or_retryable(
    status: int, error: dict[str, object], retryable: bool, text: str
) -> None:
    response = httpx.Response(status, json={"error": error} if error else {})
    found = graph_error(response, "post", "Instagram")
    assert (found.retryable, text in found.message) == (retryable, True)


def test_the_meta_app_needs_its_id_and_secret() -> None:
    assert instagram_client(meta_settings("")) is None
    no_secret = meta_settings().model_copy(update={"meta_app_secret": " "})
    assert instagram_client(no_secret) is None
    client = instagram_client(meta_settings(config_id=CONFIG_ID))
    assert client is not None
    assert (client.client_id, client.authorize_url) == (APP_ID, AUTHORIZE_URL)
    assert client.authorize_params == {"config_id": CONFIG_ID}
    assert (client.scopes, client.token_method) == (SCOPES, "GET")
    token = Token(access_token="EAA-1", refresh_token=None, expires_at=None)
    assert client.refresh_grant is exchange_grant
    assert exchange_grant(token) == {
        "grant_type": "fb_exchange_token",
        "fb_exchange_token": "EAA-1",
    }
