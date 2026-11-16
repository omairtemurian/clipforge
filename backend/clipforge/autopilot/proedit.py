"""The autopilot's Pro Edit variants (SPEC-v3 1.5, 3.8, 6).

With a campaign's "Also make a Pro Edit variant" switch on and its
allow_heavy_edits "true", every pending draft the autopilot makes also gets a
Pro Edit variant of its clip, made with the autopilot's preset and at most its
intensity. Anything else (the switch off, allow_heavy_edits "false" or
"unknown", Pro Edit turned off in config.yaml, a monthly cap used up) makes
none. The variant is a separate clip linked to the original: the original's
draft stays as it is and the owner approves the original, the variant or both
in the Approval Inbox; the autopilot never approves anything.
"""

import logging

from sqlalchemy import Engine

from clipforge import config, usage
from clipforge.models import AutopilotSettings, Campaign, ProEditOptions

logger = logging.getLogger(__name__)


def wants_variants(campaign: Campaign, autopilot: AutopilotSettings) -> bool:
    """Whether the autopilot of campaign makes Pro Edit variants: its switch
    is on and the campaign says heavy edits are allowed."""
    return autopilot.proedit_enabled and campaign.allow_heavy_edits == "true"


def variant_options(autopilot: AutopilotSettings) -> ProEditOptions:
    """The options of an autopilot variant: the campaign's preset at its
    maximum intensity, the other choices the defaults."""
    return ProEditOptions(
        preset=autopilot.proedit_preset, intensity=autopilot.proedit_max_intensity
    )


def start_variants(
    engine: Engine,
    campaign: Campaign,
    autopilot: AutopilotSettings,
    clip_ids: list[int],
) -> list[int]:
    """Queue a Pro Edit variant of each clip of clip_ids (rendered clips of
    campaign's project that have a pending draft) if wants_variants; return
    the ids of the variant clips. A clip whose variant cannot be made is
    logged and skipped, never raised, and nothing starts while a monthly
    usage cap is used up."""
    if not clip_ids or not wants_variants(campaign, autopilot):
        return []
    if not config.settings.proedit.enabled:
        return []
    try:
        usage.check_caps(engine)
    except usage.UsageCapExceeded as error:
        logger.warning("autopilot: no Pro Edit variants: %s", error)
        return []
    # Pro Edit runs need process, which imports the autopilot pipeline.
    from clipforge.proedit.runs import start_run

    options = variant_options(autopilot)
    started: list[int] = []
    for clip_id in clip_ids:
        try:
            started.append(start_run(engine, clip_id, options).clip.id)
        except Exception:
            logger.exception("autopilot: no Pro Edit variant of clip %d", clip_id)
    return started
