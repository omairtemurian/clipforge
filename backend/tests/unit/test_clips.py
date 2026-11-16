"""Tests of a project's clips: saving scored candidates, their layouts and
render status."""

import shutil
from pathlib import Path

import pytest
from builders import FIXTURE_LAUGHS
from clipforge.captions_templates import clip_template, get_template
from clipforge.clip_layouts import set_planned_layouts
from clipforge.clips import render_clip_row, save_clips
from clipforge.db import ClipRow
from clipforge.models import (
    CandidateList,
    CaptionColors,
    CaptionStyle,
    ClipCandidate,
    FaceBox,
    ProcessingSettings,
    ScoredCandidate,
    Scores,
    SignalList,
)
from clipforge.pipeline.reframe import ClipSpan, crop_path, plan_crop
from clipforge.pipeline.step import SIGNALS, TRANSCRIPT, StepError, write_json
from fakes import FIXTURES, LLM_RESPONSE
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session, select

# llm_response.json, with LLM averages D 64, A 82, B 73.5, C 68 and E 75.
D, A, B, C, E = CandidateList.model_validate_json(LLM_RESPONSE.read_bytes()).clips
SETTINGS = ProcessingSettings(auto_cut=False, auto_zoom=False)


def with_scores(c: ClipCandidate, overall: int, laugh: float = 0.0) -> ScoredCandidate:
    """Return c with its LLM scores and this overall and laugh score, and an
    energy score of 0.5."""
    scores = Scores(
        overall=overall,
        hook=c.hook,
        flow=c.flow,
        value=c.value,
        trend=c.trend,
        laugh=laugh,
        energy=0.5,
    )
    return ScoredCandidate(**c.model_dump(), scores=scores)


def face(center_x: float) -> FaceBox:
    """Return a 100 px face centered at center_x, 300 px from the top."""
    return FaceBox(x=center_x - 50, y=300.0, width=100.0, height=100.0, score=0.9)


def test_save_clips_adds_scored_candidates_as_candidate_clips_in_order(
    engine: Engine, tmp_path: Path
) -> None:
    project_id = add_project(engine)
    processing = ProcessingSettings(
        num_clips=2, caption_template="clean", auto_cut=False, auto_zoom=False
    )
    scored = [with_scores(C, 74), with_scores(A, 71, laugh=0.9), with_scores(D, 61)]

    # Without remove_fillers and auto_cut, the (empty) work directory is not
    # read.
    ids = save_clips(engine, project_id, scored, processing, tmp_path)

    with Session(engine) as session:
        rows = {row.id: row for row in session.exec(select(ClipRow)).all()}
    assert sorted(rows) == sorted(ids)
    saved = [rows[clip_id].to_model() for clip_id in ids]
    # All of them, in their order: score already kept the best num_clips.
    assert [(c.title, c.start, c.end, c.scores) for c in saved] == [
        (C.title, 35.8, 59.5, scored[0].scores),
        (A.title, 0.5, 35.2, scored[1].scores),
        (D.title, 1.5, 32.9, scored[2].scores),
    ]
    clip_a = saved[1]
    assert (clip_a.project_id, clip_a.status, clip_a.output_path) == (
        project_id,
        "candidate",
        None,
    )
    assert (clip_a.layout, clip_a.caption_template) == ("fill", "clean")
    assert (clip_a.hook_text, clip_a.description, clip_a.reason) == (
        A.hook_text,
        A.description,
        A.reason,
    )
    assert (clip_a.hashtags, clip_a.emphasis_words) == (A.hashtags, A.emphasis_words)
    assert clip_a.scores == Scores(
        overall=71, hook=88, flow=84, value=80, trend=76, laugh=0.9, energy=0.5
    )
    assert (clip_a.cut_ranges, clip_a.caption_overrides) == ([], [])
    assert not clip_a.auto_cut


def test_save_clips_follows_the_headline_caption_and_color_settings(
    engine: Engine, tmp_path: Path
) -> None:
    project_id = add_project(engine)
    processing = SETTINGS.model_copy(
        update={"auto_headline": False, "captions": False, "auto_color": True}
    )

    [clip_id] = save_clips(
        engine, project_id, [with_scores(A, 71)], processing, tmp_path
    )

    with Session(engine) as session:
        clip = session.get_one(ClipRow, clip_id).to_model()
    assert (clip.hook_text, clip.show_captions, clip.auto_color) == ("", False, True)


def test_save_clips_gives_the_clips_the_preset_caption_colors(
    engine: Engine, tmp_path: Path
) -> None:
    project_id = add_project(engine)
    processing = SETTINGS.model_copy(
        update={
            "caption_template": "neon_lime",
            "caption_colors": CaptionColors(
                primary_color="#FFFFFF", highlight_color="#22C55E"
            ),
        }
    )

    [clip_id] = save_clips(
        engine, project_id, [with_scores(A, 71)], processing, tmp_path
    )

    with Session(engine) as session:
        clip = session.get_one(ClipRow, clip_id).to_model()
    assert clip.caption_style == CaptionStyle(
        primary_color="#FFFFFF", highlight_color="#22C55E"
    )
    template = clip_template(clip)
    assert (template.primary_color, template.highlight_color) == ("#FFFFFF", "#22C55E")
    assert template.emphasis_color == get_template("neon_lime").emphasis_color


def test_save_clips_of_no_candidates_adds_no_clips(
    engine: Engine, tmp_path: Path
) -> None:
    project_id = add_project(engine)

    assert save_clips(engine, project_id, [], ProcessingSettings(), tmp_path) == []
    with Session(engine) as session:
        assert session.exec(select(ClipRow)).all() == []


def test_save_clips_with_remove_fillers_saves_their_filler_cuts(
    engine: Engine, tmp_path: Path
) -> None:
    project_id = add_project(engine)
    processing = ProcessingSettings(
        remove_fillers=True, auto_cut=False, auto_zoom=False
    )
    scored = [with_scores(A, 71), with_scores(C, 68)]
    with pytest.raises(StepError, match=r"transcript\.json not found"):
        save_clips(engine, project_id, scored, processing, tmp_path)
    shutil.copyfile(FIXTURES / TRANSCRIPT, tmp_path / TRANSCRIPT)
    write_json(tmp_path / SIGNALS, SignalList(list(FIXTURE_LAUGHS)))

    ids = save_clips(engine, project_id, scored, processing, tmp_path)

    # A (0.5-35.2 s) loses "Um," and "Like," with their pauses, C "Uh,".
    with Session(engine) as session:
        cuts = [session.get_one(ClipRow, clip_id).cut_ranges for clip_id in ids]
    assert cuts == [[(6.2, 7.55), (22.6, 24.15)], [(41.5, 42.85)]]


def test_save_clips_with_auto_cut_merges_its_silence_cuts_with_filler_cuts(
    engine: Engine, tmp_path: Path
) -> None:
    project_id = add_project(engine)
    shutil.copyfile(FIXTURES / TRANSCRIPT, tmp_path / TRANSCRIPT)
    write_json(tmp_path / SIGNALS, SignalList(list(FIXTURE_LAUGHS)))
    both = ProcessingSettings(remove_fillers=True)
    assert both.auto_cut

    (clip_id,) = save_clips(engine, project_id, [with_scores(A, 71)], both, tmp_path)

    # A (0.5-35.2 s): the silences of auto cut, and "Um," (6.2-7.55) and
    # "Like," (22.6-24.15) of remove_fillers merged with the pauses around
    # them.
    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
    assert row.auto_cut
    assert row.cut_ranges == [
        (3.02, 3.33),
        (6.17, 7.58),
        (10.62, 10.98),
        (19.82, 20.13),
        (22.57, 24.18),
        (27.22, 27.53),
        (30.17, 30.53),
    ]


def test_render_clip_row_needs_an_existing_clip(engine: Engine, tmp_path: Path) -> None:
    with pytest.raises(StepError, match="clip 42 not found"):
        render_clip_row(engine, 42, tmp_path)


def test_set_planned_layouts_gives_clips_the_layout_of_their_crop_plan(
    engine: Engine, tmp_path: Path
) -> None:
    ids = save_clips(
        engine,
        add_project(engine),
        [with_scores(A, 71), with_scores(D, 61)],
        SETTINGS,
        tmp_path,
    )
    two_faces = [[face(300.0), face(900.0)]] * 10
    for clip_id, faces in zip(ids, (two_faces, [[]] * 10), strict=True):
        plan = plan_crop(ClipSpan(clip_id, 0.0, 1.0), "9:16", (1280, 720), faces, [])
        write_json(crop_path(tmp_path, clip_id), plan)

    set_planned_layouts(engine, tmp_path, ids)

    with Session(engine) as session:
        layouts = [session.get_one(ClipRow, clip_id).layout for clip_id in ids]
    assert layouts == ["split", "fill"]


def test_render_clip_row_needs_the_crop_plan(engine: Engine, tmp_path: Path) -> None:
    (clip_id,) = save_clips(
        engine, add_project(engine), [with_scores(A, 71)], SETTINGS, tmp_path
    )

    with pytest.raises(StepError, match=r"crop_\d+\.json not found; run the reframe"):
        render_clip_row(engine, clip_id, tmp_path)
    with pytest.raises(StepError, match=r"crop_\d+\.json not found"):
        set_planned_layouts(engine, tmp_path, [clip_id])

    with Session(engine) as session:
        clip = session.get_one(ClipRow, clip_id)
    assert (clip.status, clip.layout) == ("candidate", "fill")


def test_render_clip_row_needs_the_transcript_for_the_captions(
    engine: Engine, tmp_path: Path
) -> None:
    (clip_id,) = save_clips(
        engine, add_project(engine), [with_scores(A, 71)], SETTINGS, tmp_path
    )
    work = tmp_path / "work"
    work.mkdir()
    no_faces: list[list[FaceBox]] = [[] for _ in range(10)]
    plan = plan_crop(ClipSpan(clip_id, 0.0, 1.0), "9:16", (1280, 720), no_faces, [])
    write_json(crop_path(work, clip_id), plan)

    with pytest.raises(StepError, match=r"transcript\.json not found; run the"):
        render_clip_row(engine, clip_id, work)

    with Session(engine) as session:
        clip = session.get_one(ClipRow, clip_id)
    assert (clip.status, clip.output_path) == ("candidate", None)
    assert [path.name for path in work.iterdir()] == [f"crop_{clip_id}.json"]


def test_save_clips_with_auto_zoom_gives_clips_their_punch_ins(
    engine: Engine, tmp_path: Path
) -> None:
    shutil.copyfile(FIXTURES / TRANSCRIPT, tmp_path / TRANSCRIPT)
    write_json(tmp_path / SIGNALS, SignalList(list(FIXTURE_LAUGHS)))
    zoom = ProcessingSettings(auto_cut=False)
    assert zoom.auto_zoom

    (clip_id,) = save_clips(
        engine, add_project(engine), [with_scores(A, 71)], zoom, tmp_path
    )

    with Session(engine) as session:
        row = session.get_one(ClipRow, clip_id)
    assert (row.auto_zoom, row.cut_ranges) == (True, [])
    # A (0.5-35.2 s) emphasizes "yoga", "floor", "fridges" and "cheese"; the
    # new sentences at 6.63, 23.13 and 27.53 s are 3 s or more from them.
    assert [(k.t, k.scale) for k in row.zoom_keyframes[1::4]] == [
        (2.53, 1.15),
        (6.63, 1.12),
        (12.99, 1.15),
        (19.24, 1.15),
        (23.13, 1.12),
        (27.53, 1.12),
        (32.43, 1.15),
    ]
