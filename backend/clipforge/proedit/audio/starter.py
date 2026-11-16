"""The recommended CC0 starter set of sound effects (SPEC-v3 5.5), built from
Freesound by scripts/fetch_starter_sfx.py once the owner has a key.

Nothing is downloaded at install time. build_starter_set searches each
group of STARTER_GROUPS (a Freesound tag, a length range, how many sounds)
and downloads the CC0 sounds only (CC BY ones are skipped, so the set needs
no credits) into the library, tagged "starter" and with the group's
category. Only the generated table of licenses (licenses_markdown) is meant
for the repository, never the audio, which lives under data/.
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

import httpx
from sqlmodel import Session

from clipforge.assets import update_asset
from clipforge.models import Asset
from clipforge.proedit.audio.freesound import (
    FreesoundClient,
    FreesoundSound,
    download_sound,
)
from clipforge.proedit.audio.licenses import needs_credit
from clipforge.stock.base import StockError

logger = logging.getLogger(__name__)
STARTER_TAG = "starter"
CANDIDATES = 40


@dataclass(frozen=True, slots=True)
class StarterGroup:
    """A kind of sound the starter set holds: the Freesound tag to search,
    the category it gets, its length range in seconds and how many to keep."""

    tag: str
    category: str
    min_s: float
    max_s: float
    count: int


STARTER_GROUPS = (
    StarterGroup("whoosh", "whoosh", 0.2, 2.5, 6),
    StarterGroup("impact", "impact", 0.3, 4.0, 5),
    StarterGroup("riser", "riser", 1.0, 6.0, 4),
    StarterGroup("click", "click", 0.02, 0.6, 3),
    StarterGroup("pop", "click", 0.02, 0.8, 3),
    StarterGroup("ding", "chime", 0.3, 3.0, 3),
)


@dataclass(frozen=True, slots=True)
class StarterSound:
    """A sound of the starter set: the Freesound sound and its asset."""

    sound: FreesoundSound
    asset: Asset


def build_starter_set(
    client: FreesoundClient,
    session: Session,
    groups: Sequence[StarterGroup] = STARTER_GROUPS,
    transport: httpx.BaseTransport | None = None,
) -> list[StarterSound]:
    """Download the CC0 sounds of groups into the library and return them
    (a sound that is in the library already is not downloaded again).

    A group that Freesound cannot search or whose sounds cannot be
    downloaded is logged and keeps what it has; raises StockError only if
    no group could be searched.
    """
    found: list[StarterSound] = []
    searched = 0
    for group in groups:
        try:
            candidates = client.search(
                tags=[group.tag],
                min_duration_s=group.min_s,
                max_duration_s=group.max_s,
                page_size=CANDIDATES,
            )
        except StockError as exc:
            logger.warning("starter %s: search failed: %s", group.tag, exc)
            continue
        searched += 1
        kept = 0
        for sound in (c for c in candidates if not needs_credit(c.license)):
            if kept >= group.count:
                break
            try:
                asset = download_sound(
                    session,
                    sound,
                    kind="sfx",
                    category=group.category,
                    transport=transport,
                )
            except StockError as exc:
                logger.warning("starter %s: %s skipped: %s", group.tag, sound.id, exc)
                continue
            asset = update_asset(
                session, asset.id, tags=list(dict.fromkeys([*asset.tags, STARTER_TAG]))
            )
            found.append(StarterSound(sound, asset))
            kept += 1
    if groups and not searched:
        raise StockError("Freesound could not be searched for any group")
    return found


def licenses_markdown(sounds: Sequence[StarterSound]) -> str:
    """Return the table of licenses of sounds, as the repository keeps it
    (no audio): category, Freesound page, license and credit."""
    rows = [
        f"| {s.asset.category} | <{s.sound.page_url}> | {s.sound.license} "
        f"| {s.sound.attribution.replace('|', chr(92) + '|')} |"
        for s in sorted(sounds, key=lambda s: (s.asset.category or "", s.sound.id))
    ]
    header = [
        "# Starter sound effects (generated, no audio)",
        "",
        "Written by `scripts/fetch_starter_sfx.py`: the CC0 sounds it downloaded",
        "from Freesound into `data/audio/freesound/`. The audio is not committed.",
        "",
        "| Category | Source | License | Credit |",
        "| --- | --- | --- | --- |",
    ]
    return "\n".join([*header, *rows, ""])
