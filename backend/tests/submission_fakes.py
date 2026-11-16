"""Helpers of the submission tracker and campaign account tests (tests
only): published posts of campaign projects."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

from campaign_api import in_campaign
from clipforge import campaigns, posts
from clipforge.models import Campaign, CampaignCreate, SocialPlatform
from seed import add_clip
from social_fakes import add_account, clip_of, set_rights, write_video
from sqlalchemy import Engine

T0 = datetime(2030, 1, 15, 9, 0, tzinfo=UTC)
URL = "https://www.youtube.com/shorts/abc123"


def new_campaign(engine: Engine, **fields: object) -> Campaign:
    """Add a campaign with a credit line, hashtags and instructions."""
    data: dict[str, object] = {
        "name": "Pizza Clips",
        "required_credit_line": "Clip of Chef Mario",
        "required_hashtags": ["pizza", "clips"],
        "required_tags_mentions": ["@chefmario"],
        "submission_instructions": "Paste the link in #submit",
        "rate_per_1k_usd": 1.5,
    } | fields
    return campaigns.create_campaign(engine, CampaignCreate.model_validate(data))


def campaign_clip(engine: Engine, campaign_id: int | None, title: str = "Clip") -> int:
    """Add a rendered clip of a new project of the campaign; its id."""
    project_id = in_campaign(engine, campaign_id)
    set_rights(engine, project_id, "own")
    clip_id = add_clip(engine, project_id, "rendered", 70, title)
    output = clip_of(engine, clip_id).output_path
    assert output is not None
    write_video(Path(output))
    return clip_id


def account(
    engine: Engine, platform: SocialPlatform = "youtube", name: str = "main"
) -> int:
    """Connect the account called name on platform; its id."""
    return add_account(engine, f"{platform}-{name}", platform)


def publish(
    engine: Engine, clip_id: int, account_id: int, url: str | None = URL, hour: int = 1
) -> int:
    """Make a post of the clip to the account that is published at url (or
    without one); its id."""
    at = T0 + timedelta(hours=hour)
    post = posts.create_post(
        engine,
        clip_id=clip_id,
        account_id=account_id,
        payload={"title": "Post"},
        scheduled_at=at,
    )
    posts.queue_post(engine, post.id, at)
    posts.move(engine, post.id, "uploading", attempts=1, attempted_at=at)
    posts.move(engine, post.id, "published", url=url, external_post_id=f"x{post.id}")
    return post.id
