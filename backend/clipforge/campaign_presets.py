"""Campaign presets (SPEC-v2 3.18): applying a campaign to a project sets
what the campaign asks for, so that its clips pass the rule checker
(campaign_rules).

The project gets the campaign (project.campaign_id), the length presets
that cover the campaign's duration range, its caption template and its
required credit line as the project's credit line. Each clip of the
project gets the caption template, the required hashtags (first) and, at
the end of its description, the credit line and the tags/mentions that it
lacks. Clips that a job saves later get the same text (preset_new_clips).
The platforms that a campaign allows are read from the campaign when a
clip is checked or published.
"""

from collections.abc import Sequence
from typing import get_args

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from clipforge.campaign_rows import CampaignRow
from clipforge.campaign_rules import has_credit_line, has_mention
from clipforge.campaigns import CampaignNotFound
from clipforge.candidate_rules import PRESET_LENGTH_RANGES
from clipforge.captions_templates import load_templates
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import (
    Campaign,
    LengthPreset,
    ProcessingSettings,
    Project,
)

# The most hashtags and the longest description that the clip editor saves
# (ClipPatch); required hashtags are kept even past the cap.
HASHTAGS_MAX = 8
DESCRIPTION_MAX = 300
ELLIPSIS = "…"


class ProjectNotFound(LookupError):
    """No project has the id."""


class UnknownCaptionTemplate(ValueError):
    """A campaign names a caption template that does not exist."""


def check_caption_template(name: str | None) -> None:
    """Raise UnknownCaptionTemplate if name (None: none) is not a caption
    template; the message lists the known ones."""
    templates = load_templates()
    if name is not None and name not in templates:
        known = ", ".join(templates)
        raise UnknownCaptionTemplate(
            f"caption_template: unknown template {name!r} (known: {known})"
        )


# Presets that cover several finer ones; a campaign lists the finer ones.
BROAD_PRESETS = ("0_60", "60_180")


def length_presets_for(campaign: Campaign) -> list[LengthPreset] | None:
    """Return the length presets whose ranges overlap the campaign's
    duration range, shortest first; None if the campaign sets no range or no
    preset overlaps it (the project keeps its presets then)."""
    low, high = campaign.min_duration_s, campaign.max_duration_s
    if low is None and high is None:
        return None
    low, high = low or 0.0, high or float("inf")
    presets = [
        preset
        for preset in get_args(LengthPreset)
        if preset in PRESET_LENGTH_RANGES
        and preset not in BROAD_PRESETS
        and PRESET_LENGTH_RANGES[preset][0] < high
        and PRESET_LENGTH_RANGES[preset][1] > low
    ]
    return presets or None


def preset_settings(
    settings: ProcessingSettings, campaign: Campaign
) -> ProcessingSettings:
    """Return settings with the campaign's length presets and caption
    template (each only if the campaign sets one)."""
    changes: dict[str, object] = {}
    presets = length_presets_for(campaign)
    if presets is not None:
        changes["length_presets"] = presets
    if campaign.caption_template is not None:
        changes["caption_template"] = campaign.caption_template
    return settings.model_copy(update=changes)


def preset_text(
    description: str, hashtags: Sequence[str], campaign: Campaign
) -> tuple[str, list[str]]:
    """Return a clip's description and hashtags with what the campaign
    requires: the required hashtags first, then the clip's others up to
    HASHTAGS_MAX; the credit line and the missing tags/mentions on their own
    lines after the description, which is shortened (with "…") to keep the
    whole within DESCRIPTION_MAX characters when it can."""
    tags = _hashtags(hashtags, campaign.required_hashtags)
    lines = []
    line = campaign.required_credit_line.strip()
    if line and not has_credit_line(description, line):
        lines.append(line)
    mentions = [
        m
        for m in campaign.required_tags_mentions
        if not has_mention(tags, description, m)
    ]
    if mentions:
        lines.append(" ".join(mentions))
    if not lines:
        return description, tags
    return _with_lines(description, "\n".join(lines)), tags


def apply_campaign(engine: Engine, project_id: int, campaign_id: int | None) -> Project:
    """Make campaign_id the project's campaign and apply its preset to the
    project and its clips; return the project. With None the project leaves
    its campaign and keeps its settings and clips as they are.

    Raise ProjectNotFound, CampaignNotFound or UnknownCaptionTemplate (if
    the campaign's template no longer exists); nothing changes then.
    """
    with Session(engine) as session:
        row = session.get(ProjectRow, project_id)
        if row is None:
            raise ProjectNotFound(f"project {project_id} not found")
        row.campaign_id = campaign_id
        if campaign_id is not None:
            campaign = _campaign(session, campaign_id)
            check_caption_template(campaign.caption_template)
            row.settings = preset_settings(row.settings, campaign)
            if campaign.required_credit_line.strip():
                row.credit_line = campaign.required_credit_line.strip()
            clips = session.exec(
                select(ClipRow).where(col(ClipRow.project_id) == project_id)
            )
            for clip in clips:
                _preset_clip(session, clip, campaign, campaign.caption_template)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def preset_new_clips(engine: Engine, project_id: int, clip_ids: Sequence[int]) -> None:
    """Give the clips clip_ids, just saved for project_id, its campaign's
    text (preset_text) and, if the campaign sets a caption template, the
    project's caption template: the campaign's, which the preset gave the
    project, or the one its autopilot chose (autopilot.pipeline). Nothing
    if the project has no campaign."""
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        if project is None or project.campaign_id is None:
            return
        campaign = _campaign(session, project.campaign_id)
        template = (
            None
            if campaign.caption_template is None
            else project.settings.caption_template
        )
        for clip_id in clip_ids:
            clip = session.get(ClipRow, clip_id)
            if clip is not None:
                _preset_clip(session, clip, campaign, template)
        session.commit()


def _preset_clip(
    session: Session, clip: ClipRow, campaign: Campaign, template: str | None
) -> None:
    """Give clip the caption template (None: keep its own) and the
    campaign's text."""
    if template is not None:
        clip.caption_template = template
    clip.description, clip.hashtags = preset_text(
        clip.description, clip.hashtags, campaign
    )
    session.add(clip)


def _campaign(session: Session, campaign_id: int) -> Campaign:
    row = session.get(CampaignRow, campaign_id)
    if row is None:
        raise CampaignNotFound(f"campaign {campaign_id} not found")
    return row.to_model()


def _hashtags(own: Sequence[str], required: Sequence[str]) -> list[str]:
    """Return required, then the tags of own that are not among them (any
    letter case), up to HASHTAGS_MAX in all."""
    taken = {tag.casefold() for tag in required}
    others = [tag for tag in own if tag.lstrip("#").casefold() not in taken]
    room = max(HASHTAGS_MAX - len(required), 0)
    return [*required, *others[:room]]


def _with_lines(description: str, lines: str) -> str:
    """Return description followed by lines after a blank line, the
    description shortened with ELLIPSIS so the result fits DESCRIPTION_MAX
    (unless lines alone do not fit)."""
    text = description.rstrip()
    if not text:
        return lines
    room = DESCRIPTION_MAX - len(lines) - 2
    if len(text) > room and room > len(ELLIPSIS):
        text = text[: room - len(ELLIPSIS)].rstrip() + ELLIPSIS
    return f"{text}\n\n{lines}"
