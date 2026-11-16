"""A clip's segments and its timeline (SPEC-v2 3.5, 4): the video track
that plays the segments, moving the span that the segments cover, the
rules of the other tracks (track_problems) and their items as the render
draws and mixes them (clip_layers).

Migration 004_v2_timeline builds the same video track for v1 clips in SQL:
item ids are "video-<index>" there and here.
"""

import logging
from collections.abc import Collection, Iterator, Mapping, Sequence
from pathlib import Path
from typing import cast

from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlmodel import Session

from clipforge.assets import get_asset
from clipforge.fonts import available_fonts
from clipforge.models import (
    Asset,
    AssetKind,
    AudioProps,
    BrollProps,
    Clip,
    MusicProps,
    OverlayProps,
    SourceSpan,
    TextProps,
    Timeline,
    TrackItem,
    TrackItemKind,
    TrackName,
    VoiceoverProps,
)
from clipforge.pipeline.hooks import Punch, clip_punch, hook_layers
from clipforge.pipeline.sections import played_spans
from clipforge.pipeline.text_overlay import MAX_TEXT_LAYERS, text_layer_problems
from clipforge.pipeline.timeline_graph import (
    AUDIO_TRACKS,
    VISUAL_TRACKS,
    Layer,
    LayerProps,
)

logger = logging.getLogger(__name__)

# The kinds of item that each track holds.
TRACK_ITEM_KINDS: dict[TrackName, frozenset[TrackItemKind]] = {
    "video": frozenset({"source"}),
    "broll": frozenset({"video", "image"}),
    "overlays": frozenset({"video", "image"}),
    "text": frozenset({"text"}),
    "music": frozenset({"audio"}),
    "sfx": frozenset({"audio"}),
    "voiceover": frozenset({"audio"}),
}
# The asset kinds that an item of each kind plays (source and text: none).
ITEM_ASSET_KINDS: dict[TrackItemKind, frozenset[AssetKind]] = {
    "video": frozenset({"video"}),
    "image": frozenset({"image", "logo"}),
    "audio": frozenset({"audio", "music", "sfx"}),
}
# The props of each track's items (the video track's have none).
TRACK_PROPS: dict[TrackName, type[BaseModel]] = {
    "broll": BrollProps,
    "overlays": OverlayProps,
    "text": TextProps,
    "music": MusicProps,
    "sfx": AudioProps,
    "voiceover": VoiceoverProps,
}
LAYER_TRACKS: tuple[TrackName, ...] = (*VISUAL_TRACKS, *AUDIO_TRACKS)
# How far past the clip's end an item may end: float noise, not a frame.
END_SLACK_S = 0.001

_SEGMENTS: TypeAdapter[list[SourceSpan]] = TypeAdapter(list[SourceSpan])


def video_items(segments: Sequence[SourceSpan]) -> list[TrackItem]:
    """Return the video track that plays segments in order: a "source" item
    with id video-<index> for each."""
    return [
        TrackItem(id=f"video-{index}", kind="source", start=start, end=end)
        for index, (start, end) in enumerate(segments)
    ]


def timeline_of(segments: Sequence[SourceSpan]) -> Timeline:
    """Return the timeline of a clip that plays segments: its video track
    (video_items), every other track empty."""
    return Timeline(video=video_items(segments))


def with_segments(tracks: Timeline, segments: Sequence[SourceSpan]) -> Timeline:
    """Return tracks with its video track replaced by video_items(segments);
    the other tracks are kept."""
    return tracks.model_copy(update={"video": video_items(segments)})


def respan(
    segments: Sequence[SourceSpan], start: float, end: float
) -> list[SourceSpan]:
    """Return segments, in their order, with the earliest one in the source
    starting at start and the latest one ending at end (a single segment
    becomes [start, end]).

    Raises ValueError if that leaves a segment with end <= start.
    """
    moved = [list(span) for span in segments]
    earliest = min(range(len(moved)), key=lambda index: moved[index][0])
    latest = max(range(len(moved)), key=lambda index: moved[index][1])
    moved[earliest][0], moved[latest][1] = start, end
    try:
        return _SEGMENTS.validate_python([tuple(span) for span in moved])
    except ValidationError as exc:
        raise ValueError(f"segments {moved} are not valid") from exc


def clip_length(clip: Clip, fps: int) -> float:
    """Return how many seconds the rendered clip lasts: its segments less its
    cuts, in whole frames at fps (sections.played_spans), as the render cuts
    it."""
    spans = played_spans(clip.start, clip.end, clip.segments, clip.cut_ranges, fps)
    return sum(end - start for start, end in spans)


def track_problems(
    tracks: Timeline,
    length: float,
    assets: Mapping[int, Asset],
    fonts: Collection[str],
) -> list[str]:
    """Return what is wrong with the tracks other than video of a clip whose
    render lasts length seconds; an empty list if nothing is.

    Item ids must be unique across the timeline. Each item must be of a
    kind its track holds (TRACK_ITEM_KINDS), lie inside the rendered clip,
    play an asset of assets (by id) of a kind it plays (ITEM_ASSET_KINDS)
    whose file exists (a text item plays none), and have props its track
    accepts (TRACK_PROPS), a text item's font being one of fonts. The
    text track holds at most MAX_TEXT_LAYERS items.
    """
    problems = text_layer_problems(tracks.text)
    seen: set[str] = set()
    for track in TRACK_ITEM_KINDS:
        for item in getattr(tracks, track):
            label = f"{track} item {item.id!r}"
            if item.id in seen:
                problems.append(f"{label}: another item has the id {item.id!r}")
            seen.add(item.id)
            if track == "video":
                continue
            problems += [
                f"{label}: {problem}"
                for problem in _item_problems(track, item, length, assets, fonts)
            ]
    return problems


def tidy_props(tracks: Timeline) -> Timeline:
    """Return tracks with each item's props as its track's props model
    reads them, defaults filled in (the items must be valid:
    track_problems)."""
    tidy: dict[str, list[TrackItem]] = {
        track: [
            item.model_copy(update={"props": _tidy(track, item.props)})
            for item in getattr(tracks, track)
        ]
        for track in LAYER_TRACKS
    }
    return tracks.model_copy(update=tidy)


def _tidy(track: TrackName, props: dict[str, object]) -> dict[str, object]:
    """Return props as track's props model reads them (TRACK_PROPS)."""
    return TRACK_PROPS[track].model_validate(props).model_dump()


def timeline_assets(session: Session, tracks: Timeline) -> dict[int, Asset]:
    """Return the assets, by id, that the items of tracks play and that
    exist in the library."""
    ids = {
        item.asset_id
        for track in LAYER_TRACKS
        for item in getattr(tracks, track)
        if item.asset_id is not None
    }
    found = {asset_id: get_asset(session, asset_id) for asset_id in sorted(ids)}
    return {asset_id: asset for asset_id, asset in found.items() if asset}


def clip_layers(session: Session, clip: Clip, fps: int) -> list[Layer]:
    """Return the layers of clip's timeline that its render draws and mixes,
    in order: B-roll, overlays and text, then music, sound effects and
    voiceover, each track's items in its order (later ones on top).

    Each item ends by the end of the rendered clip (clip_length at fps);
    an item that starts after that, or whose props, asset, file or font is
    no longer valid (an edit or a deleted asset since it was saved), is
    left out and logged, as are the text items after the first
    MAX_TEXT_LAYERS. The layers of the clip's viral hook come last (its
    text on top; pipeline/hooks.hook_layers).
    """
    length = clip_length(clip, fps)
    assets, fonts = timeline_assets(session, clip.tracks), available_fonts()
    layers = []
    for track in LAYER_TRACKS:
        for index, item in enumerate(getattr(clip.tracks, track)):
            fitted = item.model_copy(update={"end": min(item.end, length)})
            problems = list(_item_problems(track, fitted, length, assets, fonts))
            if item.start >= length:
                problems.append(f"it starts after the clip ends ({length:g} s)")
            if track == "text" and index >= MAX_TEXT_LAYERS:
                problems.append(f"only the first {MAX_TEXT_LAYERS} text items show")
            if problems:
                logger.warning(
                    "clip %d: %s item %r left out: %s",
                    clip.id,
                    track,
                    item.id,
                    "; ".join(problems),
                )
                continue
            props = cast(LayerProps, TRACK_PROPS[track].model_validate(item.props))
            path = _layer_path(props, item, assets, fonts)
            layers.append(Layer(track, fitted, props, path))
    return layers + hook_layers(clip.hook, length, fonts)


def hook_punch(clip: Clip, fps: int) -> Punch | None:
    """Return the punch-in of clip's viral hook in its render at fps
    (pipeline/hooks.clip_punch); None if it has none."""
    return clip_punch(clip.hook, clip_length(clip, fps))


def _item_problems(
    track: TrackName,
    item: TrackItem,
    length: float,
    assets: Mapping[int, Asset],
    fonts: Collection[str],
) -> Iterator[str]:
    """Yield what is wrong with item on track (not video) of a clip whose
    render lasts length seconds (see track_problems)."""
    if item.kind not in TRACK_ITEM_KINDS[track]:
        allowed = ", ".join(sorted(TRACK_ITEM_KINDS[track]))
        yield f"kind {item.kind!r} is not one of this track's ({allowed})"
        return
    if item.end > length + END_SLACK_S:
        yield (
            f"[{item.start:g}, {item.end:g}] s is not inside the clip, "
            f"which lasts {length:g} s"
        )
    yield from _asset_problems(item, assets)
    try:
        props = TRACK_PROPS[track].model_validate(item.props)
    except ValidationError as exc:
        for error in exc.errors():
            where = ".".join(str(part) for part in error["loc"])
            yield f"props {where}: {error['msg']}"
        return
    if isinstance(props, TextProps) and props.font not in fonts:
        yield f"font {props.font!r} is not a bundled or uploaded font"


def _asset_problems(item: TrackItem, assets: Mapping[int, Asset]) -> Iterator[str]:
    """Yield what is wrong with item's asset: none for a text item, else
    one of assets of a kind it plays whose file exists."""
    kinds = ITEM_ASSET_KINDS.get(item.kind)
    if kinds is None:
        if item.asset_id is not None:
            yield f"a {item.kind} item plays no asset"
        return
    if item.asset_id is None:
        yield f"a {item.kind} item needs an asset_id"
        return
    asset = assets.get(item.asset_id)
    if asset is None:
        yield f"asset {item.asset_id} does not exist"
    elif asset.kind not in kinds:
        yield (
            f"asset {asset.id} is a {asset.kind}, not one of {', '.join(sorted(kinds))}"
        )
    elif not Path(asset.path).is_file():
        yield f"the file of asset {asset.id} ({asset.path}) is missing"


def _layer_path(
    props: LayerProps,
    item: TrackItem,
    assets: Mapping[int, Asset],
    fonts: Mapping[str, Path],
) -> Path:
    """Return the file a valid item plays (its asset's) or draws with (a
    text item's font)."""
    if isinstance(props, TextProps):
        return fonts[props.font]
    assert item.asset_id is not None
    return Path(assets[item.asset_id].path)
