"""Credits of the CC BY sounds a Pro Edit uses (SPEC-v3 5.6).

A CC BY asset must be credited wherever its sound is used. The assets that a
Pro Edit's SFX and music bed items play (by library asset id) that are CC BY
give their attribution lines; with_credits appends them to a clip's
description under "Sound credits:", so the description (and with it the
export JSON of the clip, pipeline/export.clip_metadata, and the post text
that starts from it) carries them. CC0 sounds and the bundled sounds need no
credit.
"""

from collections.abc import Iterable, Sequence

from sqlmodel import Session

from clipforge.db import ClipRow
from clipforge.models import Asset
from clipforge.proedit.audio.licenses import needs_credit
from clipforge.proedit.audio.sounds import library_assets
from clipforge.proedit.edl import TypedEdlItem

HEADING = "Sound credits:"


def used_assets(session: Session, items: Sequence[TypedEdlItem]) -> list[Asset]:
    """Return the library sounds that an SFX or music bed item of items plays,
    each once, in order of first use; ids of no asset or of a non-sound
    asset are left out."""
    assets = library_assets(session, items).values()
    return list({asset.id: asset for asset in assets}.values())


def credit_lines(assets: Iterable[Asset]) -> list[str]:
    """Return the attribution of each CC BY asset of assets with one, once,
    in order."""
    lines = (a.attribution.strip() for a in assets if needs_credit(a.license))
    return list(dict.fromkeys(line for line in lines if line))


def with_credits(text: str, lines: Sequence[str]) -> str:
    """Return text with the credit lines that it does not have yet appended
    under HEADING (added once); text itself when it has them all."""
    missing = [line for line in lines if line not in text]
    if not missing:
        return text
    bullets = "\n".join(f"- {line}" for line in missing)
    if HEADING in text:
        return f"{text.rstrip()}\n{bullets}"
    separator = "\n\n" if text.strip() else ""
    return f"{text.rstrip()}{separator}{HEADING}\n{bullets}"


def credit_clip(session: Session, row: ClipRow, assets: Iterable[Asset]) -> list[str]:
    """Append the credits of the CC BY assets to the description of the clip
    row and save it; return the credit lines of assets (all of them, also
    those that the description had already)."""
    lines = credit_lines(assets)
    description = with_credits(row.description, lines)
    if description != row.description:
        row.description = description
        session.add(row)
        session.commit()
    return lines
