"""The asset catalog the LLM Director may use (SPEC-v3 3.5): ids and tags
only, never paths. It holds the bundled original SFX pack and music loops
(by file stem, so Pro Edit works without a library or key), the library's
sound assets (by asset id) and the procedural overlays; an overlay may also
be any "emoji:<glyph>" (overlays/procedural).

catalog_problems lists the items of a plan that name an asset the catalog
does not hold (or an overlay that cannot be drawn), so the Director's reply
is sent back instead of failing at render time.
"""

from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from clipforge.models import Asset, EdlItem
from clipforge.pipeline.music import BUNDLED_TRACKS
from clipforge.pipeline.sfx import BUNDLED_SFX
from clipforge.proedit.overlays.procedural import PROCEDURAL_ASSETS, asset_problem

CatalogKind = Literal["sfx", "music", "overlay"]
# The library asset kinds that are SFX and music beds.
LIBRARY_KINDS: dict[str, CatalogKind] = {
    "sfx": "sfx",
    "audio": "sfx",
    "music": "music",
}
# The item kind that plays each catalog kind.
ITEM_KIND: dict[str, CatalogKind] = {
    "sfx": "sfx",
    "music_bed": "music",
    "overlay": "overlay",
}


class CatalogAsset(BaseModel):
    """An asset the Director may name: its id (what params.asset says),
    what it is and its tags (category and mood of a tagged library sound
    included)."""

    id: str
    kind: CatalogKind
    tags: list[str]


def _library_entry(asset: Asset) -> CatalogAsset | None:
    kind = LIBRARY_KINDS.get(asset.kind)
    if kind is None:
        return None
    extra = [tag for tag in (asset.category, asset.mood) if tag]
    tags = [*dict.fromkeys([*asset.tags, *extra])]
    return CatalogAsset(id=str(asset.id), kind=kind, tags=tags)


def asset_catalog(library: Iterable[Asset] = ()) -> list[CatalogAsset]:
    """Return the catalog: the bundled sounds and loops, the sound assets of
    library (others are left out) and the procedural overlays."""
    bundled = [
        CatalogAsset(id=Path(s.file).stem, kind="sfx", tags=list(s.tags))
        for s in BUNDLED_SFX
    ]
    loops = [
        CatalogAsset(id=Path(t.file).stem, kind="music", tags=list(t.tags))
        for t in BUNDLED_TRACKS
    ]
    own = [entry for a in library if (entry := _library_entry(a)) is not None]
    overlays = [
        CatalogAsset(id=name, kind="overlay", tags=["procedural"])
        for name in PROCEDURAL_ASSETS
    ]
    return [*bundled, *loops, *own, *overlays]


def catalog_problems(
    items: Sequence[EdlItem], catalog: Sequence[CatalogAsset]
) -> list[str]:
    """List the items that name an asset the catalog lacks for their kind
    (an overlay may also be an emoji the bundled font draws)."""
    known = {(entry.kind, entry.id) for entry in catalog}
    problems: list[str] = []
    for item in items:
        kind = ITEM_KIND.get(item.kind)
        asset = item.params.get("asset")
        if kind is None or not isinstance(asset, str):
            continue
        if kind == "overlay":
            why = asset_problem(asset)
        elif (kind, asset) in known:
            why = None
        else:
            why = f"asset {asset!r} is not a {kind} asset of the catalog"
        if why is not None:
            problems.append(f"item {item.id} ({item.kind}): {why}")
    return problems
