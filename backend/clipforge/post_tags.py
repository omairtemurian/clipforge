"""Which hashtags a generated post text must carry (steering, owner request
2026-11-02): the always_hashtags setting, the target account's own and the
required hashtags of the project's campaign, in that order, without
repeats (any letter case). Everything that writes post text (post_copy,
quick post, the bulk scheduler's default text) asks here; the autopilot's
drafts must too.
"""

from sqlalchemy import Engine
from sqlmodel import Session

from clipforge import config
from clipforge.campaign_rows import CampaignRow
from clipforge.db import ProjectRow
from clipforge.models import SocialAccount
from clipforge.required_tags import clean_tags


def required_hashtags(
    engine: Engine, project_id: int, account: SocialAccount | None = None
) -> list[str]:
    """Return the hashtags that a post of a clip of project_id to account
    (None: no particular account) must carry: the global ones, the
    account's and the campaign's."""
    with Session(engine) as session:
        project = session.get(ProjectRow, project_id)
        campaign = (
            None
            if project is None or project.campaign_id is None
            else session.get(CampaignRow, project.campaign_id)
        )
        campaign_tags = (
            [] if campaign is None else campaign.to_model().required_hashtags
        )
    own = [] if account is None else account.always_hashtags
    return clean_tags([*config.settings.always_hashtags, *own, *campaign_tags])
