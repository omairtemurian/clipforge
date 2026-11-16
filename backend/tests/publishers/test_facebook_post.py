"""Tests for a Facebook reel's settings (clipforge.models.FacebookPostOptions,
clipforge.publishers.facebook_post): pure helpers, no network."""

from pathlib import Path

import pytest
from builders import make_clip
from clipforge.models import FacebookPostOptions
from clipforge.publishers.base import PublishError, clip_caption
from clipforge.publishers.facebook import SCOPES, facebook_client
from clipforge.publishers.facebook_api import can_create
from clipforge.publishers.facebook_post import (
    check_video,
    options_of,
    publish_body,
    reel_state,
)
from facebook_publish_fakes import recorded
from instagram_publish_fakes import APP_ID, meta_settings
from pydantic import ValidationError

CLIP = make_clip("karaoke_bold", segments=[(10.0, 40.0)], title="Big moment")


def test_options_clean_page_ids_and_ignore_other_platform_keys() -> None:
    options = FacebookPostOptions.model_validate(
        {"collaborator_page_ids": [" 104739358734099 "], "privacy_level": "SELF_ONLY"}
    )
    assert options.collaborator_page_ids == ["104739358734099"]
    assert options.ai_generated is False


@pytest.mark.parametrize(
    "payload",
    [
        {"collaborator_page_ids": ["page"]},
        {"collaborator_page_ids": ["1234567"] * 11},
        {"ai_generated": "sometimes"},
    ],
)
def test_options_refuse_what_facebook_refuses(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        FacebookPostOptions.model_validate(payload)
    with pytest.raises(PublishError, match="settings are invalid"):
        options_of(payload)


def test_publish_body_defaults_to_the_clip_caption() -> None:
    body = publish_body(FacebookPostOptions(), CLIP, "77")
    assert body == {
        "video_id": "77",
        "upload_phase": "finish",
        "video_state": "PUBLISHED",
        "description": clip_caption(CLIP),
    }
    assert clip_caption(CLIP).startswith("Big moment")
    blank = publish_body(FacebookPostOptions(description=" ", title=" "), CLIP, "77")
    assert "description" not in blank and "title" not in blank


def test_video_checks(tmp_path: Path) -> None:
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"x" * 10)
    assert check_video(video, CLIP) == 10
    with pytest.raises(PublishError, match="MP4"):
        check_video(tmp_path / "clip.webm", CLIP)
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")
    with pytest.raises(PublishError, match="empty"):
        check_video(empty, CLIP)
    long = make_clip("karaoke_bold", segments=[(0.0, 91.0)])
    with pytest.raises(PublishError, match="3 to 90 s"):
        check_video(video, long)


@pytest.mark.parametrize(
    ("name", "state", "retryable"),
    [
        ("status_processing", "pending", None),
        ("status_published", "published", None),
        ("status_processing_error", "failed", False),
        ("status_expired", "failed", True),
    ],
)
def test_the_status_of_a_reel(name: str, state: str, retryable: bool | None) -> None:
    found, error = reel_state(recorded(name))
    assert found == state
    assert (error.retryable if error else None) is retryable
    assert reel_state({}) == ("pending", None)


def test_the_status_reports_an_upload_that_failed() -> None:
    found, error = reel_state({"status": {"video_status": "upload_failed"}})
    assert found == "failed" and error is not None and error.retryable


def test_a_page_needs_the_create_content_task() -> None:
    assert can_create({"tasks": ["CREATE_CONTENT"]})
    assert not can_create({"tasks": ["ANALYZE"]})
    assert can_create({})


def test_the_client_uses_the_meta_app_and_the_page_permissions() -> None:
    client = facebook_client(meta_settings())
    assert client is not None and client.client_id == APP_ID
    assert (
        client.scopes
        == SCOPES
        == (
            "pages_show_list",
            "pages_read_engagement",
            "pages_manage_posts",
        )
    )
    assert facebook_client(meta_settings("")) is None
