"""The sounds that Pro Edit SFX and music bed items play (SPEC-v3 3.3, 5).

An item's params.asset names its sound: a library asset id (digits; the
caller resolves the ids it may play to files, library_sounds), a sound of
the bundled original pack (pipeline/sfx.BUNDLED_SFX, assets/sfx) or a
bundled music loop (pipeline/music.BUNDLED_TRACKS, assets/music) by its
file name with or without the extension ("whoosh_swift" or
"night_drive.flac"), so a Pro Edit works without any library or key. A
sound's length is read with ffprobe once per file version (sound_seconds);
whether the configured ffmpeg has a filter (rubberband is only in some
builds) once per binary (ffmpeg_has).
"""

from collections.abc import Mapping, Sequence
from functools import lru_cache
from pathlib import Path

from sqlmodel import Session

from clipforge.assets import get_asset
from clipforge.ffmpeg import ffmpeg_bin, ffprobe_json, run_ffmpeg
from clipforge.models import Asset
from clipforge.pipeline.music import BUNDLED_TRACKS, MUSIC_DIR
from clipforge.pipeline.sfx import BUNDLED_SFX, SFX_DIR, BundledSfx
from clipforge.proedit.edl import MusicBedItem, SfxItem, TypedEdlItem

# The library asset kinds an SFX item may play.
SOUND_KINDS = frozenset({"sfx", "audio", "music"})
SoundItem = SfxItem | MusicBedItem


def sfx_items(items: Sequence[TypedEdlItem]) -> list[SfxItem]:
    """Return the SFX items of items, in their order."""
    return [item for item in items if isinstance(item, SfxItem)]


def sound_items(items: Sequence[TypedEdlItem]) -> list[SoundItem]:
    """Return the items of items that play an asset (SFX and music beds),
    in their order."""
    return [item for item in items if isinstance(item, SfxItem | MusicBedItem)]


def bundled_named(name: str) -> BundledSfx | None:
    """Return the bundled sound whose file is name, with or without its
    extension, or None."""
    return next((s for s in BUNDLED_SFX if name in (s.file, Path(s.file).stem)), None)


def find_sound(asset: str, library: Mapping[str, Path]) -> Path | None:
    """Return the file of the sound asset names: library's file for a
    library asset id, the pack's file for a bundled sound's name, the loop's
    for a bundled music track's name; None if none knows it."""
    if asset in library:
        return library[asset]
    bundled = bundled_named(asset)
    if bundled is not None:
        return SFX_DIR / bundled.file
    track = next(
        (t for t in BUNDLED_TRACKS if asset in (t.file, Path(t.file).stem)), None
    )
    return None if track is None else MUSIC_DIR / track.file


def sound_problems(
    items: Sequence[TypedEdlItem], library: Mapping[str, Path]
) -> list[str]:
    """Return why the SFX and music bed items of items cannot be played: an
    asset that names no known sound or whose file is missing; empty when all
    can be."""
    files = [s.file for s in BUNDLED_SFX] + [t.file for t in BUNDLED_TRACKS]
    names = ", ".join(Path(file).stem for file in files)
    problems = []
    for item in sound_items(items):
        path = find_sound(item.params.asset, library)
        if path is None:
            problems.append(
                f"item {item.id} ({item.kind}): no sound '{item.params.asset}' "
                f"(a library asset id or one of {names})"
            )
        elif not path.is_file():
            problems.append(
                f"item {item.id} ({item.kind}): the sound file {path} is missing"
            )
    return problems


def sound_seconds(path: Path) -> float:
    """Return the length in seconds of the sound file path (ffprobe; cached
    per file version). Raises FFmpegError if ffprobe cannot read it."""
    stat = path.stat()
    return _probed_seconds(path.resolve(), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=256)
def _probed_seconds(path: Path, mtime_ns: int, size: int) -> float:
    return float(ffprobe_json(path)["format"]["duration"])


def ffmpeg_has(name: str) -> bool:
    """Return whether the configured ffmpeg has the filter name."""
    return name in _filters(ffmpeg_bin())


@lru_cache(maxsize=4)
def _filters(binary: str) -> frozenset[str]:
    """Return the filter names `binary -filters` lists (binary is the cache
    key: run_ffmpeg runs the configured one)."""
    listing = run_ffmpeg(["-filters"]).stdout.decode("utf-8", errors="replace")
    return frozenset(
        parts[1] for line in listing.splitlines() if len(parts := line.split()) > 2
    )


def library_assets(session: Session, items: Sequence[TypedEdlItem]) -> dict[str, Asset]:
    """Return the library asset of each id that an SFX or music bed item of
    items plays, by id; ids of no asset or of a non-sound asset are left
    out."""
    assets: dict[str, Asset] = {}
    for item in sound_items(items):
        name = item.params.asset
        if not name.isdigit() or name in assets:
            continue
        asset = get_asset(session, int(name))
        if asset is not None and asset.kind in SOUND_KINDS:
            assets[name] = asset
    return assets


def library_sounds(session: Session, items: Sequence[TypedEdlItem]) -> dict[str, Path]:
    """Return the file of each library asset id that an SFX or music bed
    item of items plays, by id; ids of no asset or of a non-sound asset are
    left out (so sound_problems names them)."""
    return {
        name: Path(asset.path) for name, asset in library_assets(session, items).items()
    }
