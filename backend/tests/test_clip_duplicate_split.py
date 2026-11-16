"""Tests of duplicating a clip and splitting it into two (SPEC-v2 3.5,
clip_split): the copy has the clip's edits with new item ids; the parts of a
split last as long as the clip, and what has a time goes where its time
is."""

import pytest
from builders import track_item
from clipforge import config
from clipforge.clip_edit import ClipEditError
from clipforge.clip_split import (
    duplicate_clip,
    frame_at,
    split_clip,
    split_sections,
)
from clipforge.db import ClipRow
from clipforge.models import (
    CaptionMark,
    CaptionStyle,
    Clip,
    CropPoint,
    Framing,
    SceneReframe,
    Timeline,
    Word,
    ZoomKeyframe,
)
from clipforge.timeline import clip_length, timeline_of
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session, select

FPS = config.settings.render.fps
LONG = 60.0


def word(text: str, start: float) -> Word:
    return Word(text=text, start=start, end=start + 0.3, speaker="S0", prob=1.0)


def edited_clip(engine: Engine, **changes: object) -> int:
    """Add a clip of 10-20 s with edits that have times; return its id."""
    project_id = add_project(engine)
    fields: dict[str, object] = {
        "start": 10.0,
        "end": 20.0,
        "cut_ranges": [(13.0, 14.0), (16.0, 17.0)],
        "caption_overrides": [word("one", 11.0), word("two", 18.0)],
        "caption_style": CaptionStyle(
            word_marks=[
                CaptionMark(start=11.0, emphasis=True),
                CaptionMark(start=18.0, emoji="🔥"),
            ]
        ),
        "zoom_keyframes": [
            ZoomKeyframe(t=11.0, scale=1.2),
            ZoomKeyframe(t=19.0, scale=1.1),
        ],
        "framing": Framing(
            points=[CropPoint(t=11.0, x=0.4, y=0.5), CropPoint(t=19.0, x=0.6, y=0.5)]
        ),
        "scene_reframes": [
            SceneReframe(start=10.0, end=15.0),
            SceneReframe(start=15.0, end=20.0, layout="fit"),
        ],
        "title": "Pizza",
    }
    return add_clip(engine, project_id, "rendered", 80, **(fields | changes))


def load(engine: Engine, clip_id: int) -> Clip:
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        return row.to_model()


def split(engine: Engine, clip_id: int, at: float) -> tuple[Clip, Clip]:
    """Split clip clip_id at at seconds; return the two parts."""
    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        first, second = split_clip(session, row, at, LONG)
        return first.to_model(), second.to_model()


def length(clip: Clip) -> float:
    return clip_length(clip, FPS)


def test_a_duplicate_is_a_candidate_copy_with_new_item_ids(engine: Engine) -> None:
    layers = timeline_of([(10.0, 20.0)]).model_copy(
        update={"text": [track_item("text-1", "text", 1.0, 3.0, props={"text": "hi"})]}
    )
    clip_id = edited_clip(engine, tracks=layers)
    before = load(engine, clip_id)

    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        copy = duplicate_clip(session, row).to_model()

    assert copy.id != clip_id
    assert (copy.status, copy.output_path, copy.title) == (
        "candidate",
        None,
        "Pizza (copy)",
    )
    assert copy.model_dump(
        exclude={"id", "status", "output_path", "title", "tracks"}
    ) == (before.model_dump(exclude={"id", "status", "output_path", "title", "tracks"}))
    assert copy.tracks.video == before.tracks.video
    [text] = copy.tracks.text
    assert text.id != "text-1"
    assert text.model_dump(exclude={"id"}) == before.tracks.text[0].model_dump(
        exclude={"id"}
    )
    assert load(engine, clip_id) == before


def test_split_gives_two_clips_that_last_as_long_as_the_clip(engine: Engine) -> None:
    clip_id = edited_clip(engine)
    whole = length(load(engine, clip_id))

    first, second = split(engine, clip_id, 15.0)

    assert first.id == clip_id and second.id != clip_id
    assert first.segments == [(10.0, 15.0)]
    assert second.segments == [(15.0, 20.0)]
    assert length(first) + length(second) == pytest.approx(whole, abs=1e-6)
    assert (first.status, second.status) == ("rendered", "candidate")
    assert (second.output_path, second.hook_text) == (None, "")
    assert second.title == "Pizza (part 2)"
    assert first.tracks.video[0].id == "video-0"
    assert [(i.start, i.end) for i in second.tracks.video] == [(15.0, 20.0)]


def test_a_cut_across_the_split_is_cut_in_two(engine: Engine) -> None:
    clip_id = edited_clip(engine, cut_ranges=[(13.0, 17.0)])
    whole = length(load(engine, clip_id))

    first, second = split(engine, clip_id, 15.0)

    assert first.cut_ranges == [(13.0, 15.0)]
    assert second.cut_ranges == [(15.0, 17.0)]
    assert length(first) + length(second) == pytest.approx(whole, abs=1e-6)


def test_what_has_a_time_goes_where_its_time_is(engine: Engine) -> None:
    clip_id = edited_clip(engine)

    first, second = split(engine, clip_id, 15.0)

    assert [w.text for w in first.caption_overrides] == ["one"]
    assert [w.text for w in second.caption_overrides] == ["two"]
    assert first.caption_style.word_marks == [CaptionMark(start=11.0, emphasis=True)]
    assert second.caption_style.word_marks == [CaptionMark(start=18.0, emoji="🔥")]
    assert [k.t for k in first.zoom_keyframes] == [11.0]
    assert [k.t for k in second.zoom_keyframes] == [19.0]
    assert [p.t for p in first.framing.points] == [11.0]
    assert [p.t for p in second.framing.points] == [19.0]
    assert [(s.start, s.end, s.layout) for s in first.scene_reframes] == [
        (10.0, 15.0, "fill")
    ]
    assert [(s.start, s.end, s.layout) for s in second.scene_reframes] == [
        (15.0, 20.0, "fit")
    ]


def test_layer_items_follow_the_time_the_first_part_lasts(engine: Engine) -> None:
    # The clip plays 9 s (10-20 s less a 1 s cut); the split is at 4 s.
    layers = timeline_of([(10.0, 20.0)]).model_copy(
        update={
            "text": [
                track_item("early", "text", 1.0, 3.0),
                track_item("late", "text", 6.0, 8.0),
            ],
            "music": [
                track_item("song", "audio", 0.0, 9.0, asset_id=5, props={"volume": 0.5})
            ],
        }
    )
    clip_id = edited_clip(engine, tracks=layers, cut_ranges=[(18.0, 19.0)])

    first, second = split(engine, clip_id, 14.0)

    assert [(i.id, i.start, i.end) for i in first.tracks.text] == [("early", 1.0, 3.0)]
    assert [(i.id, i.start, i.end) for i in second.tracks.text] == [("late", 2.0, 4.0)]
    [head] = first.tracks.music
    [tail] = second.tracks.music
    assert (head.start, head.end, head.props) == (0.0, 4.0, {"volume": 0.5})
    assert (tail.start, tail.end, tail.props) == (
        0.0,
        5.0,
        {"volume": 0.5, "offset": 4.0},
    )
    assert tail.asset_id == 5


def test_split_between_two_sections_and_inside_a_rearranged_clip(
    engine: Engine,
) -> None:
    segments = [(30.0, 32.0), (10.0, 12.0), (20.0, 23.0)]
    clip_id = add_clip(
        engine,
        add_project(engine),
        "candidate",
        80,
        segments=segments,
        tracks=timeline_of(segments),
    )
    whole = length(load(engine, clip_id))

    first, second = split(engine, clip_id, 11.0)

    assert first.segments == [(30.0, 32.0), (10.0, 11.0)]
    assert second.segments == [(11.0, 12.0), (20.0, 23.0)]
    assert length(first) + length(second) == pytest.approx(whole, abs=1 / FPS)
    assert [i.id for i in first.tracks.video] == ["video-0", "video-1"]


def test_the_time_snaps_to_a_frame_of_the_clip(engine: Engine) -> None:
    clip = load(engine, edited_clip(engine))

    assert frame_at(clip, 15.0 + 0.004, FPS) == 15.0
    assert frame_at(clip, 15.0 + 0.03, FPS) == pytest.approx(15.0 + 1 / FPS, abs=1e-6)


def test_split_sections_edges() -> None:
    sections = [(30.0, 32.0), (10.0, 12.0)]

    assert split_sections(sections, 11.0) == (
        [(30.0, 32.0), (10.0, 11.0)],
        [(11.0, 12.0)],
    )
    assert split_sections(sections, 10.0) == ([(30.0, 32.0)], [(10.0, 12.0)])
    assert split_sections(sections, 32.0) == ([(30.0, 32.0)], [(10.0, 12.0)])
    for at in (5.0, 20.0, 12.0, 30.0):
        with pytest.raises(ClipEditError, match="no section plays"):
            split_sections(sections, at)


def test_a_split_that_leaves_nothing_changes_nothing(engine: Engine) -> None:
    clip_id = edited_clip(engine, cut_ranges=[(10.0, 15.0)])
    before = load(engine, clip_id)

    with Session(engine) as session:
        row = session.get(ClipRow, clip_id)
        assert row is not None
        with pytest.raises(ClipEditError, match="leave nothing"):
            split_clip(session, row, 15.0, LONG)
        with pytest.raises(ClipEditError, match="no section plays"):
            split_clip(session, row, 25.0, LONG)

    assert load(engine, clip_id) == before
    with Session(engine) as session:
        assert len(session.exec(select(ClipRow)).all()) == 1


def test_empty_timeline_clips_split(engine: Engine) -> None:
    clip_id = edited_clip(
        engine, tracks=Timeline(video=timeline_of([(10.0, 20.0)]).video)
    )

    first, second = split(engine, clip_id, 12.0)

    assert first.end == 12.0 and second.start == 12.0
