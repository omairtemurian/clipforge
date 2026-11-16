"""Campaign creator watch (SPEC-v2 3.18): the YouTube channels of a campaign's
source_channel_urls are registered in Auto Import, so the creator's new
uploads become projects within minutes.

A channel that the campaign registered carries campaign_id. Its projects get
the campaign's preset (preset_settings, credit line, campaign_id), are queued
at CAMPAIGN_PRIORITY and are "fresh uploads" (Project.fresh_upload) for
FRESH_UPLOAD_HOURS. The channel's source rights are "permission" only while
the campaign's permission evidence is complete, else unset. The channels are
watched (enabled) while the campaign is active and its end date is not past;
sync_channels brings them in line whenever the campaign changes.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Engine

from clipforge import auto_import, campaigns, config
from clipforge.campaign_presets import preset_settings
from clipforge.models import (
    Campaign,
    ProcessingSettings,
    SourceRights,
    WatchedChannel,
    WatchedChannelCreate,
    YouTubeChannelRef,
)
from clipforge.watch import youtube_handles

CAMPAIGN_RIGHTS: SourceRights = "permission"
_CHANNEL_REF = TypeAdapter(YouTubeChannelRef)

Resolver = Callable[[str], str]


@dataclass
class CampaignWatch:
    """The result of sync_channels: the campaign's watched channels and, for
    each link that could not be watched, why (url, reason)."""

    channels: list[WatchedChannel] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)


def default_resolver(handle: str) -> str:
    """Return the "UC..." id of a channel @handle (YouTube Data API)."""
    return youtube_handles.resolve_handle(handle, config.settings.youtube_api_key)


def is_open(campaign: Campaign, today: date) -> bool:
    """Whether the campaign is active and its end date (if any) is not past."""
    return campaign.status == "active" and (
        campaign.end_date is None or today <= campaign.end_date
    )


def load_campaign(engine: Engine, channel: WatchedChannel) -> Campaign | None:
    """Return the campaign that registered channel, None if the owner added it
    (or its campaign is gone)."""
    if channel.campaign_id is None:
        return None
    try:
        return campaigns.get_campaign(engine, channel.campaign_id)
    except campaigns.CampaignNotFound:
        return None


def is_watched(engine: Engine, channel: WatchedChannel, today: date) -> bool:
    """Whether the channel's new videos are imported: it is enabled and, for
    a campaign's channel, the campaign is open (is_open). An end date passes
    without anyone syncing, so this is checked at each import."""
    if not channel.enabled:
        return False
    campaign = load_campaign(engine, channel)
    return campaign is None or is_open(campaign, today)


def channel_rights(campaign: Campaign) -> SourceRights | None:
    """The source rights of a campaign channel's projects: "permission" once
    the campaign's permission evidence is complete, else None."""
    return None if campaigns.permission_missing(campaign) else CAMPAIGN_RIGHTS


def sync_channels(
    engine: Engine,
    campaign: Campaign,
    today: date,
    resolve: Resolver = default_resolver,
) -> CampaignWatch:
    """Register the YouTube channels in the campaign's source_channel_urls in
    Auto Import and drop those it registered for links that were removed.

    A new channel is watched with the campaign's preset settings, credit line
    and source rights (a project's own are taken from the campaign when it is
    imported, see youtube_watcher); a channel that the owner already watches is adopted
    unless another campaign has it. Each channel is enabled while
    the campaign is open (is_open). Links that are not a YouTube channel, an
    @handle that cannot be looked up and channels of another campaign are
    skipped with the reason.
    """
    watch = CampaignWatch()
    wanted: dict[str, str] = {}
    for url in campaign.source_channel_urls:
        try:
            wanted.setdefault(_channel_id(str(url), resolve), str(url))
        except ValueError as exc:
            watch.skipped.append((str(url), str(exc)))
        except youtube_handles.HandleError as exc:
            watch.skipped.append((str(url), str(exc)))
    auto_import.remove_campaign_channels(engine, campaign.id, keep=wanted)
    for channel_id, url in wanted.items():
        try:
            watch.channels.append(_watch(engine, campaign, channel_id, today))
        except auto_import.ChannelExists as exc:
            watch.skipped.append((url, str(exc)))
    return watch


def _channel_id(url: str, resolve: Resolver) -> str:
    """Return the "UC..." id of the YouTube channel that url names; ValueError
    if it names none."""
    try:
        ref = _CHANNEL_REF.validate_python(url)
    except ValidationError as exc:
        raise ValueError(f"not a YouTube channel link: {url}") from exc
    return resolve(ref) if ref.startswith("@") else ref


def _watch(
    engine: Engine, campaign: Campaign, channel_id: str, today: date
) -> WatchedChannel:
    """Watch channel_id for the campaign (adding or adopting it) and enable it
    while the campaign is open."""
    enabled = is_open(campaign, today)
    existing = auto_import.find_channel(engine, channel_id)
    if existing is None:
        create = WatchedChannelCreate(
            channel=channel_id,
            settings=preset_settings(ProcessingSettings(), campaign),
            source_rights=channel_rights(campaign),
            credit_line=campaign.required_credit_line.strip(),
        )
        return auto_import.add_channel(
            engine, create, campaign_id=campaign.id, enabled=enabled
        )
    if existing.campaign_id not in (None, campaign.id):
        raise auto_import.ChannelExists(
            f"channel {channel_id} is watched for campaign {existing.campaign_id}"
        )
    fields: dict[str, object] = {"campaign_id": campaign.id, "enabled": enabled}
    if existing.source_rights is None and channel_rights(campaign) is not None:
        fields["source_rights"] = CAMPAIGN_RIGHTS
    auto_import.set_channel_fields(engine, existing.id, **fields)
    return auto_import.get_channel(engine, existing.id)
