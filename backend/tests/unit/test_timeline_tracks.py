"""Tests of a clip's timeline tracks (SPEC-v2 3.5, clipforge.timeline): the
rules of each track (kinds, times inside the rendered clip, assets, props)
and the layers a render draws and mixes."""

from pathlib import Path

import pytest
from builders import make_clip
from builders import track_item as item
from clipforge.assets import add_asset, delete_asset
from clipforge.fonts import available_fonts
from clipforge.models import (
    Asset,
    AssetKind,
    MusicProps,
    Timeline,
    TrackItem,
)
from clipforge.timeline import (
    clip_layers,
    clip_length,
    tidy_props,
    timeline_of,
    track_problems,
)
from sqlalchemy import Engine
from sqlmodel import Session

FPS = 30
# make_clip's clip is 10-12.5 s: 2.5 s rendered without cuts.
LENGTH = 2.5


def asset(asset_id: int, kind: AssetKind, path: Path) -> Asset:
    """Return an asset of kind whose file is path."""
    return Asset(
        id=asset_id,
        kind=kind,
        path=str(path),
        license="CC0-1.0",
        attribution="",
        source_url=None,
        tags=[],
    )


@pytest.fixture
def files(tmp_path: Path) -> dict[int, Asset]:
    """Assets 1 (video), 2 (image), 3 (music) and 4 (logo) with files, and
    5 (image) whose file is missing."""
    paths = {name: tmp_path / name for name in ("a.mp4", "b.png", "c.mp3", "d.png")}
    for path in paths.values():
        path.write_bytes(b"x")
    return {
        1: asset(1, "video", paths["a.mp4"]),
        2: asset(2, "image", paths["b.png"]),
        3: asset(3, "music", paths["c.mp3"]),
        4: asset(4, "logo", paths["d.png"]),
        5: asset(5, "image", tmp_path / "gone.png"),
    }


def problems_of(files: dict[int, Asset], **tracks: list[TrackItem]) -> list[str]:
    """Return track_problems of make_clip's timeline with tracks."""
    timeline = timeline_of([(10.0, 12.5)]).model_copy(update=tracks)
    return track_problems(timeline, LENGTH, files, available_fonts())


def test_one_valid_item_on_each_track_has_no_problems(
    files: dict[int, Asset],
) -> None:
    assert (
        problems_of(
            files,
            broll=[item("b", "video", 0, 1, asset_id=1, props={"offset": 2})],
            overlays=[item("o", "image", 0.5, 2.5, asset_id=4)],
            text=[item("t", "text", 0, 2.5, props={"text": "Hi", "font": "Anton"})],
            music=[item("m", "audio", 0, 2.5, asset_id=3, props={"volume": 0.3})],
            sfx=[item("s", "audio", 1, 1.2, asset_id=3)],
            voiceover=[item("v", "audio", 2, 2.5005, asset_id=3)],
        )
        == []
    )


def test_items_must_lie_inside_the_rendered_clip(files: dict[int, Asset]) -> None:
    (problem,) = problems_of(files, sfx=[item("s", "audio", 2, 2.6, asset_id=3)])

    assert (
        problem == "sfx item 's': [2, 2.6] s is not inside the clip, which lasts 2.5 s"
    )


def test_cuts_shorten_the_clip_the_items_must_fit_in() -> None:
    clip = make_clip("minimal", cut_ranges=[(10.5, 11.0)])

    assert clip_length(clip, FPS) == pytest.approx(2.0)


def test_an_item_whose_end_is_not_after_its_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="end must be after its start"):
        item("t", "text", 1, 1)


def test_each_track_holds_only_its_kinds(files: dict[int, Asset]) -> None:
    problems = problems_of(
        files,
        music=[item("m", "image", 0, 1, asset_id=2)],
        text=[item("t", "source", 0, 1)],
    )

    assert problems == [
        "text item 't': kind 'source' is not one of this track's (text)",
        "music item 'm': kind 'image' is not one of this track's (audio)",
    ]


def test_unknown_kinds_are_refused_by_the_model() -> None:
    with pytest.raises(ValueError, match="kind"):
        item("x", "sticker", 0, 1)


def test_assets_must_exist_match_the_kind_and_have_their_file(
    files: dict[int, Asset],
) -> None:
    problems = problems_of(
        files,
        broll=[
            item("missing", "video", 0, 1, asset_id=99),
            item("wrong", "video", 0, 1, asset_id=3),
            item("nofile", "image", 0, 1, asset_id=5),
            item("none", "image", 0, 1),
        ],
        text=[item("t", "text", 0, 1, asset_id=2, props={"text": "a"})],
    )

    assert problems == [
        "broll item 'missing': asset 99 does not exist",
        "broll item 'wrong': asset 3 is a music, not one of video",
        f"broll item 'nofile': the file of asset 5 ({files[5].path}) is missing",
        "broll item 'none': a image item needs an asset_id",
        "text item 't': a text item plays no asset",
    ]


def test_props_are_checked_against_their_track(files: dict[int, Asset]) -> None:
    problems = problems_of(
        files,
        overlays=[item("o", "image", 0, 1, asset_id=2, props={"opacity": 2})],
        text=[
            item("t", "text", 0, 1, props={}),
            item("f", "text", 0, 1, props={"text": "a", "font": "Comic Sans"}),
        ],
        music=[item("m", "audio", 0, 1, asset_id=3, props={"loop": True})],
    )

    assert problems == [
        "overlays item 'o': props opacity: Input should be less than or equal to 1",
        "text item 't': props text: Field required",
        "text item 'f': font 'Comic Sans' is not a bundled or uploaded font",
        "music item 'm': props loop: Extra inputs are not permitted",
    ]


def test_item_ids_are_unique_across_tracks(files: dict[int, Asset]) -> None:
    problems = problems_of(
        files, text=[item("video-0", "text", 0, 1, props={"text": "a"})]
    )

    assert problems == ["text item 'video-0': another item has the id 'video-0'"]


def test_tidy_props_fills_in_the_defaults() -> None:
    timeline = Timeline(sfx=[item("s", "audio", 0, 1, asset_id=3)])

    assert tidy_props(timeline).sfx[0].props == {"volume": 1.0, "offset": 0.0}


def test_clip_layers_cut_items_to_the_clip_and_leave_out_broken_ones(
    engine: Engine, tmp_path: Path
) -> None:
    music = tmp_path / "music.mp3"
    music.write_bytes(b"x")
    with Session(engine) as session:
        kept = add_asset(session, "music", str(music), "CC0-1.0")
        gone = add_asset(session, "music", str(music), "CC0-1.0")
        delete_asset(session, gone.id)
        tracks = timeline_of([(10.0, 12.5)]).model_copy(
            update={
                "music": [
                    item("long", "audio", 1, 9, asset_id=kept.id),
                    item("late", "audio", 3, 4, asset_id=kept.id),
                    item("deleted", "audio", 0, 1, asset_id=gone.id),
                ],
                "text": [item("t", "text", 0, 1, props={"text": "Hi"})],
            }
        )
        layers = clip_layers(session, make_clip("minimal", tracks=tracks), FPS)

    assert [(layer.track, layer.item.id, layer.item.end) for layer in layers] == [
        ("text", "t", 1.0),
        ("music", "long", LENGTH),
    ]
    assert layers[0].path == available_fonts()["Montserrat ExtraBold"]
    assert layers[1].path == music
    assert layers[1].props == MusicProps()
