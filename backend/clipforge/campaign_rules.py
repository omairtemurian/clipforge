"""The campaign rule checker (SPEC-v2 3.18): whether a clip may be published
for its project's campaign.

Every rule gives a RuleResult (pass or fail, with what to fix); publishing
is blocked while one fails (api.campaign_rules.require_campaign_rules). The
rules: the campaign is active and its end date has not passed, its
permission evidence is complete, the project's source rights are set
(SPEC-v2 1.6, the only rule of a project without a campaign), the clip's
played length is within the campaign's minimum and maximum, the clip has
the required hashtags, credit line and tags/mentions, and the platform is
one the campaign allows. The text matchers are shared with
campaign_presets, which adds what the checker would ask for.
"""

import re
from collections.abc import Sequence
from datetime import date

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge.campaign_rows import CampaignRow
from clipforge.campaigns import permission_missing
from clipforge.db import ClipRow, ProjectRow
from clipforge.models import (
    Campaign,
    CampaignCheck,
    CampaignRule,
    Clip,
    Project,
    RuleResult,
    SocialPlatform,
)
from clipforge.pipeline.caption_lines import to_ms
from clipforge.pipeline.frame_cuts import cut_spans


class ClipNotFound(LookupError):
    """No clip has the id."""


def played_length(clip: Clip) -> float:
    """Return how long the clip plays, in seconds (to the millisecond): its
    segments without the parts that its cut_ranges remove."""
    total = 0
    for start, end in clip.segments:
        cut = sum(b - a for a, b in cut_spans(start, end, clip.cut_ranges))
        total += to_ms(end) - to_ms(start) - cut
    return total / 1000


def has_hashtag(hashtags: Sequence[str], description: str, tag: str) -> bool:
    """Whether a clip with hashtags and description has hashtag tag (with or
    without "#"): among its hashtags or as "#tag" in its description, in any
    letter case."""
    wanted = tag.lstrip("#").casefold()
    if any(own.lstrip("#").casefold() == wanted for own in hashtags):
        return True
    return _word_in(f"#{wanted}", description)


def has_mention(hashtags: Sequence[str], description: str, mention: str) -> bool:
    """Whether a clip's description has a required tag or mention ("@name",
    "#tag" or a word) as a whole word in any letter case; a "#tag" among its
    hashtags counts too."""
    if mention.startswith("#") and has_hashtag(hashtags, description, mention):
        return True
    return _word_in(mention, description)


def has_credit_line(description: str, credit_line: str) -> bool:
    """Whether description holds credit_line (letter case and runs of white
    space aside)."""
    return _tidy(credit_line) in _tidy(description)


def check_clip(
    clip: Clip,
    project: Project,
    campaign: Campaign | None,
    today: date,
    platform: SocialPlatform | None = None,
) -> CampaignCheck:
    """Check clip of project against the rules of campaign on day today (the
    owner's local date), to be published on platform (None: on any platform
    of the campaign). A project without a campaign is only checked for its
    source rights."""
    if campaign is None:
        results = [_source_rights(project)]
    else:
        results = [
            _campaign_status(campaign, today),
            _permission(campaign),
            _source_rights(project),
            _min_duration(clip, campaign),
            _max_duration(clip, campaign),
            _hashtags(clip, campaign),
            _credit_line(clip, campaign),
            _mentions(clip, campaign),
            _platform(campaign, platform),
        ]
    return CampaignCheck(
        clip_id=clip.id,
        campaign_id=None if campaign is None else campaign.id,
        platform=platform,
        results=results,
    )


def check_saved_clip(
    engine: Engine,
    clip_id: int,
    today: date,
    platform: SocialPlatform | None = None,
) -> CampaignCheck:
    """Check saved clip clip_id against its project's campaign (check_clip);
    raise ClipNotFound if there is no such clip."""
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        project = None if row is None else session.get(ProjectRow, row.project_id)
        if row is None or project is None:
            raise ClipNotFound(f"clip {clip_id} not found")
        campaign_row = (
            None
            if project.campaign_id is None
            else session.get(CampaignRow, project.campaign_id)
        )
        clip, project_model = row.to_model(), project.to_model()
        campaign = None if campaign_row is None else campaign_row.to_model()
    return check_clip(clip, project_model, campaign, today, platform)


def failed_message(check: CampaignCheck) -> str:
    """Return the failed rules of check as one sentence for the user."""
    details = "; ".join(r.detail for r in check.results if not r.passed)
    return f"clip {check.clip_id} breaks campaign rules: {details}"


def _campaign_status(campaign: Campaign, today: date) -> RuleResult:
    """The campaign is active and its end date (if any) is not past."""
    if campaign.status != "active":
        return _result("campaign_status", False, f"the campaign is {campaign.status}")
    end = campaign.end_date
    if end is not None and today > end:
        return _result("campaign_status", False, f"the campaign ended on {end}")
    until = "" if end is None else f" until {end}"
    return _result("campaign_status", True, f"the campaign is active{until}")


def _permission(campaign: Campaign) -> RuleResult:
    """The permission evidence (URL, screenshot, date) is complete."""
    missing = permission_missing(campaign)
    if missing:
        return _result("permission", False, f"add {', '.join(missing)}")
    return _result("permission", True, "the permission evidence is complete")


def _source_rights(project: Project) -> RuleResult:
    """The project's source rights are set (SPEC-v2 1.6)."""
    if project.source_rights is None:
        return _result("source_rights", False, "choose the project's source rights")
    return _result("source_rights", True, f"source rights: {project.source_rights}")


def _min_duration(clip: Clip, campaign: Campaign) -> RuleResult:
    """The clip plays at least the campaign's minimum length."""
    low, length = campaign.min_duration_s, played_length(clip)
    if low is None:
        return _result("min_duration", True, "no minimum length")
    if length < low:
        return _result(
            "min_duration", False, f"the clip is {length:g}s, under {low:g}s"
        )
    return _result("min_duration", True, f"{length:g}s, at least {low:g}s")


def _max_duration(clip: Clip, campaign: Campaign) -> RuleResult:
    """The clip plays at most the campaign's maximum length."""
    high, length = campaign.max_duration_s, played_length(clip)
    if high is None:
        return _result("max_duration", True, "no maximum length")
    if length > high:
        return _result(
            "max_duration", False, f"the clip is {length:g}s, over {high:g}s"
        )
    return _result("max_duration", True, f"{length:g}s, at most {high:g}s")


def _hashtags(clip: Clip, campaign: Campaign) -> RuleResult:
    """The clip has every required hashtag."""
    required = campaign.required_hashtags
    if not required:
        return _result("hashtags", True, "no hashtags required")
    missing = [
        f"#{tag}"
        for tag in required
        if not has_hashtag(clip.hashtags, clip.description, tag)
    ]
    if missing:
        return _result("hashtags", False, f"add {' '.join(missing)}")
    return _result("hashtags", True, " ".join(f"#{tag}" for tag in required))


def _credit_line(clip: Clip, campaign: Campaign) -> RuleResult:
    """The clip's description holds the required credit line."""
    line = campaign.required_credit_line.strip()
    if not line:
        return _result("credit_line", True, "no credit line required")
    if not has_credit_line(clip.description, line):
        return _result("credit_line", False, f'add "{line}" to the description')
    return _result("credit_line", True, "the description has the credit line")


def _mentions(clip: Clip, campaign: Campaign) -> RuleResult:
    """The clip's description has every required tag or mention."""
    required = campaign.required_tags_mentions
    if not required:
        return _result("mentions", True, "no tags or mentions required")
    missing = [
        m for m in required if not has_mention(clip.hashtags, clip.description, m)
    ]
    if missing:
        return _result("mentions", False, f"add {' '.join(missing)} to the description")
    return _result("mentions", True, " ".join(required))


def _platform(campaign: Campaign, platform: SocialPlatform | None) -> RuleResult:
    """The platform is one that the campaign allows (with none given: the
    campaign allows at least one)."""
    allowed = campaign.allowed_platforms
    if not allowed:
        return _result("platform", False, "the campaign lists no allowed platform")
    listed = ", ".join(allowed)
    if platform is None:
        return _result("platform", True, f"allowed: {listed}")
    if platform not in allowed:
        return _result(
            "platform", False, f"the campaign allows {listed}, not {platform}"
        )
    return _result("platform", True, f"{platform} is allowed")


def _result(rule: CampaignRule, passed: bool, detail: str) -> RuleResult:
    return RuleResult(rule=rule, passed=passed, detail=detail)


def _word_in(word: str, text: str) -> bool:
    """Whether word stands alone in text (not inside a longer word, mention
    or hashtag), in any letter case."""
    pattern = rf"(?<![\w@#]){re.escape(word)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _tidy(text: str) -> str:
    return " ".join(text.split()).casefold()
