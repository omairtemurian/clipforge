"""The asset library: logos, fonts, music and other files that clips use,
each with its license and attribution (SPEC-v2 1.3, 4).

The helpers take a Session and commit. The fonts bundled in assets/fonts and
the music loops in assets/music and the sound effects in assets/sfx are
added to the library by register_bundled_fonts, register_bundled_music and
register_bundled_sfx.
"""

from collections.abc import Sequence
from pathlib import Path

from fontTools.ttLib import TTFont
from sqlmodel import Session, col, select

from clipforge.asset_rows import AssetRow
from clipforge.fonts import FONT_SUFFIXES, FONTS_DIR
from clipforge.models import Asset, AssetKind
from clipforge.pipeline.music import BUNDLED_TRACKS, MUSIC_DIR, MUSIC_LICENSE
from clipforge.pipeline.sfx import BUNDLED_SFX, SFX_DIR, SFX_LICENSE

BUNDLED_TAG = "bundled"
UPLOADED_TAG = "uploaded"
FONT_LICENSE = "OFL-1.1"
COPYRIGHT_NAME = 0


class AssetNotFoundError(LookupError):
    """No asset has the given id."""


def add_asset(
    session: Session,
    kind: AssetKind,
    path: str,
    license: str,
    attribution: str = "",
    source_url: str | None = None,
    tags: Sequence[str] = (),
) -> Asset:
    """Add an asset to the library and return it, with its id.

    Raises a pydantic ValidationError if kind is unknown or path or license is
    empty; nothing is added then.
    """
    asset = Asset(
        id=0,
        kind=kind,
        path=path,
        license=license,
        attribution=attribution,
        source_url=source_url,
        tags=list(tags),
    )
    row = AssetRow(**asset.model_dump(exclude={"id"}))
    session.add(row)
    session.commit()
    return row.to_model()


def get_asset(session: Session, asset_id: int) -> Asset | None:
    """Return asset asset_id, or None if there is none."""
    row = session.get(AssetRow, asset_id)
    return None if row is None else row.to_model()


def list_assets(
    session: Session, kind: AssetKind | None = None, tag: str | None = None
) -> list[Asset]:
    """Return the assets in id order, only those of kind and with tag if given."""
    query = select(AssetRow).order_by(col(AssetRow.id))
    if kind is not None:
        query = query.where(AssetRow.kind == kind)
    assets = [row.to_model() for row in session.exec(query)]
    return assets if tag is None else [a for a in assets if tag in a.tags]


def update_asset(session: Session, asset_id: int, **changes: object) -> Asset:
    """Change the given fields (not id) of asset asset_id and return it.

    Raises AssetNotFoundError if there is no such asset, a TypeError if a
    name is not a changeable field and a pydantic ValidationError if a value
    is invalid; nothing is changed then.
    """
    unknown = set(changes) - (set(Asset.model_fields) - {"id"})
    if unknown:
        raise TypeError(f"not changeable asset fields: {sorted(unknown)}")
    row = session.get(AssetRow, asset_id)
    if row is None:
        raise AssetNotFoundError(asset_id)
    changed = Asset.model_validate(row, from_attributes=True).model_copy(update=changes)
    valid = Asset.model_validate(changed.model_dump())
    for name in changes:
        setattr(row, name, getattr(valid, name))
    session.add(row)
    session.commit()
    return row.to_model()


def delete_asset(session: Session, asset_id: int) -> None:
    """Delete asset asset_id from the library (not its file).

    Raises AssetNotFoundError if there is no such asset.
    """
    row = session.get(AssetRow, asset_id)
    if row is None:
        raise AssetNotFoundError(asset_id)
    session.delete(row)
    session.commit()


def register_bundled_fonts(
    session: Session, fonts_dir: Path = FONTS_DIR
) -> list[Asset]:
    """Add the font files of fonts_dir to the library and return the assets
    that were added or whose path changed.

    A bundled font is matched by its file name, so a font that was
    registered before the project moved gets its new path, and a second call
    changes nothing. Its attribution is the copyright notice of the font.
    """
    known = {
        Path(row.path).name: row
        for row in session.exec(select(AssetRow).where(AssetRow.kind == "font"))
        if BUNDLED_TAG in row.tags
    }
    changed: list[AssetRow] = []
    for path in sorted(fonts_dir.iterdir()):
        if path.suffix.lower() not in FONT_SUFFIXES:
            continue
        row = known.get(path.name)
        if row is None:
            row = AssetRow(
                kind="font",
                path=str(path),
                license=FONT_LICENSE,
                attribution=font_copyright(path),
                tags=[BUNDLED_TAG],
            )
        elif row.path == str(path):
            continue
        else:
            row.path = str(path)
        session.add(row)
        changed.append(row)
    session.commit()
    return [row.to_model() for row in changed]


def register_bundled_music(
    session: Session, music_dir: Path = MUSIC_DIR
) -> list[Asset]:
    """Add the bundled music loops (pipeline/music.BUNDLED_TRACKS) whose
    files are in music_dir to the library and return the assets that were
    added or changed (see _register_bundled)."""
    entries = [
        (track.file, MUSIC_LICENSE, track.attribution, track.tags)
        for track in BUNDLED_TRACKS
    ]
    return _register_bundled(session, "music", music_dir, entries)


def register_bundled_sfx(session: Session, sfx_dir: Path = SFX_DIR) -> list[Asset]:
    """Add the sounds of the bundled pack (pipeline/sfx.BUNDLED_SFX) whose
    files are in sfx_dir to the library and return the assets that were
    added or changed (see _register_bundled)."""
    entries = [
        (sound.file, SFX_LICENSE, sound.attribution, sound.tags)
        for sound in BUNDLED_SFX
    ]
    return _register_bundled(session, "sfx", sfx_dir, entries)


def bundled_sfx_ids(session: Session) -> dict[str, int]:
    """Return the id of each bundled sound effect asset, by file name."""
    return {
        Path(asset.path).name: asset.id
        for asset in list_assets(session, kind="sfx")
        if BUNDLED_TAG in asset.tags and asset.id is not None
    }


def _register_bundled(
    session: Session,
    kind: AssetKind,
    directory: Path,
    entries: Sequence[tuple[str, str, str, Sequence[str]]],
) -> list[Asset]:
    """Add the bundled assets of kind, entries of (file name, license,
    attribution, tags) whose files are in directory, to the library and
    return those that were added or changed.

    An asset is matched by its file name, so one registered before the
    project moved gets its new path; its license, attribution and tags
    (BUNDLED_TAG and the entry's) are set from the entry, so a second call
    changes nothing.
    """
    known = {
        Path(row.path).name: row
        for row in session.exec(select(AssetRow).where(AssetRow.kind == kind))
        if BUNDLED_TAG in row.tags
    }
    changed: list[AssetRow] = []
    for file, license_name, attribution, tags in entries:
        path = directory / file
        if not path.is_file():
            continue
        fields = (str(path), license_name, attribution, [BUNDLED_TAG, *tags])
        row = known.get(file)
        if row is None:
            row = AssetRow(kind=kind, path=fields[0], license=fields[1])
        elif (row.path, row.license, row.attribution, row.tags) == fields:
            continue
        row.path, row.license, row.attribution, row.tags = fields
        session.add(row)
        changed.append(row)
    session.commit()
    return [row.to_model() for row in changed]


def font_copyright(path: Path) -> str:
    """Return the copyright notice in the name table of the font in path."""
    with TTFont(path, lazy=True) as font:
        notice = font["name"].getDebugName(COPYRIGHT_NAME)
    return str(notice or "")
