"""Tests of the auto headline (SPEC-v2 3.5, pipeline/headline and
clip_graphics): one opening line as a text-track item in the brand style
(clipforge.brand_style), regenerated without losing the owner's edits,
made for new clips of a project with a brand template, and drawn once
(the captions leave out hook_text while it exists)."""

from pathlib import Path

import pytest
from builders import make_clip
from caption_fakes import dialogues, write
from clipforge.brand_style import DEFAULT_COLOR, DEFAULT_FONT, BrandStyle, brand_style
from clipforge.clip_graphics import write_headline
from clipforge.clips import save_clips
from clipforge.db import BrandTemplateRow, ClipRow
from clipforge.fonts import available_fonts
from clipforge.models import (
    BrandTemplate,
    CandidateList,
    ClipCandidate,
    ProcessingSettings,
    ScoredCandidate,
    Scores,
    TextProps,
)
from clipforge.pipeline.headline import (
    HEADLINE_ID,
    headline_item,
    headline_props,
    new_clip_tracks,
    with_headline,
    without_headline,
)
from clipforge.pipeline.step import TRANSCRIPT
from clipforge.timeline import timeline_of
from fakes import FIXTURES, LLM_RESPONSE, FakeLLMClient
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session

STYLE = BrandStyle("Anton", "#123456")
SETTINGS = ProcessingSettings(auto_cut=False, auto_zoom=False)
A = CandidateList.model_validate_json(LLM_RESPONSE.read_bytes()).clips[1]
BRAND = BrandTemplate(
    id=3,
    name="Acme",
    logo_path="/brand/3/logo.png",
    logo_position="br",
    logo_opacity=0.8,
    font="Bebas Neue",
    primary_color="#AA00FF",
    intro_path=None,
    outro_path=None,
)


def scored(c: ClipCandidate) -> ScoredCandidate:
    """Return c with an overall score of 71."""
    scores = Scores(
        overall=71,
        hook=c.hook,
        flow=c.flow,
        value=c.value,
        trend=c.trend,
        laugh=0.0,
        energy=0.5,
    )
    return ScoredCandidate(**c.model_dump(), scores=scores)


def test_the_brand_style_is_its_font_and_color_or_the_defaults() -> None:
    fonts = available_fonts()

    assert brand_style(BRAND, fonts) == BrandStyle("Bebas Neue", "#AA00FF")
    assert brand_style(None, fonts) == BrandStyle(DEFAULT_FONT, DEFAULT_COLOR)
    gone = BRAND.model_copy(update={"font": "Deleted Sans"})
    assert brand_style(gone, fonts) == BrandStyle(DEFAULT_FONT, "#AA00FF")
    assert DEFAULT_FONT in fonts


def test_a_headline_is_white_brand_font_text_on_a_brand_box_at_the_top() -> None:
    props = headline_props("  Why we  fell  ", STYLE)

    assert props == TextProps(
        text="Why we fell",
        font="Anton",
        size=0.04,
        color="#FFFFFF",
        box="#123456",
        box_opacity=0.95,
        x=0.5,
        y=0.12,
        animation_in="slide_down",
        animation_out="fade",
        in_seconds=0.35,
        out_seconds=0.3,
    )


def test_a_long_headline_wraps_to_two_lines_and_shrinks_to_fit() -> None:
    two = headline_props("The teacher says listen to your body", STYLE)
    wide = headline_props("Recalculating your life choices in a voice so calm", STYLE)

    assert (two.text, two.size) == ("The teacher says\nlisten to your body", 0.04)
    assert wide.text.count("\n") == 1
    longest = max(len(line) for line in wide.text.split("\n"))
    assert longest > 20
    assert wide.size == pytest.approx(0.04 * 20 / longest, abs=1e-4)


def test_the_headline_item_shows_from_the_start_for_3_s_or_the_clip() -> None:
    item = headline_item("Hi", STYLE, 12.0)
    short = headline_item("Hi", STYLE, 2.2)

    assert (item.id, item.kind, item.start, item.end) == (HEADLINE_ID, "text", 0, 3.0)
    assert TextProps.model_validate(item.props) == headline_props("Hi", STYLE)
    assert short.end == 2.2


def test_a_new_headline_goes_first_and_an_edited_one_keeps_its_style() -> None:
    other = headline_item("Note", STYLE, 9).model_copy(update={"id": "t1"})

    added = with_headline([other], "First line", STYLE, 9.0)
    edited = added[0].model_copy(
        update={"end": 2.0, "props": added[0].props | {"y": 0.3, "color": "#FF0000"}}
    )
    replaced = with_headline([other, edited], "A new headline line here", STYLE, 9.0)

    assert [item.id for item in added] == [HEADLINE_ID, "t1"]
    assert [item.id for item in replaced] == ["t1", HEADLINE_ID]
    assert replaced[1].end == 2.0
    assert replaced[1].props == edited.props | {"text": "A new headline line\nhere"}
    assert without_headline(replaced) == [other]


def test_new_clips_get_a_headline_item_only_with_a_style_and_text() -> None:
    span = (10.0, 15.0)
    tracks = timeline_of([span])

    made = new_clip_tracks(tracks, span, [(10.5, 11.0)], "Big news", STYLE, 30)
    short = new_clip_tracks(tracks, (10.0, 12.0), [(10.5, 11.0)], "Hi", STYLE, 30)

    assert [(i.id, i.start, i.end) for i in made.text] == [(HEADLINE_ID, 0, 3.0)]
    assert made.video == tracks.video
    assert short.text[0].end == pytest.approx(1.5, abs=0.04)
    assert new_clip_tracks(tracks, span, [], "Big news", None, 30) == tracks
    assert new_clip_tracks(tracks, span, [], "  ", STYLE, 30) == tracks


def test_save_clips_draws_the_headline_in_the_projects_brand_style(
    engine: Engine, tmp_path: Path
) -> None:
    project_id = add_project(engine)
    with Session(engine) as session:
        brand = BrandTemplateRow(**BRAND.model_dump(exclude={"id"}))
        session.add(brand)
        session.commit()
        brand_id = brand.id
    branded = SETTINGS.model_copy(update={"brand_template_id": brand_id})
    no_headline = branded.model_copy(update={"auto_headline": False})
    gone = SETTINGS.model_copy(update={"brand_template_id": 999})

    ids = [
        save_clips(engine, project_id, [scored(A)], settings, tmp_path)[0]
        for settings in (branded, no_headline, gone, SETTINGS)
    ]

    with Session(engine) as session:
        clips = [session.get_one(ClipRow, clip_id).to_model() for clip_id in ids]
    [item] = clips[0].tracks.text
    assert item.id == HEADLINE_ID
    props = TextProps.model_validate(item.props)
    assert props == headline_props(A.hook_text, BrandStyle("Bebas Neue", "#AA00FF"))
    assert [clip.tracks.text for clip in clips[1:]] == [[], [], []]
    assert clips[0].hook_text == clips[2].hook_text == A.hook_text


def test_the_captions_leave_out_hook_text_while_a_headline_item_exists(
    tmp_path: Path,
) -> None:
    clip = make_clip("minimal", hook_text="He ate it all")
    headed = clip.model_copy(
        update={
            "tracks": clip.tracks.model_copy(
                update={"text": [headline_item("He ate it all", STYLE, 2.5)]}
            )
        }
    )

    hooks = [line for line in dialogues(write(tmp_path, clip)) if ",Hook," in line]
    assert len(hooks) == 1
    headed_ass = dialogues(write(tmp_path, headed))
    assert [line for line in headed_ass if ",Hook," in line] == []


def test_the_llm_writes_the_headline_from_the_clips_words(tmp_path: Path) -> None:
    (tmp_path / TRANSCRIPT).write_bytes((FIXTURES / TRANSCRIPT).read_bytes())
    llm = FakeLLMClient('{"text": ""}', '{"text": " “Yoga, Then the Floor” "}')
    clip = make_clip("minimal", title="Yoga")

    assert write_headline(llm, tmp_path, clip) == "Yoga, Then the Floor"
    (system, user), _ = llm.calls
    assert "headline" in system and "maxLength" in system
    assert user == "What is said in the clip:\nsaid, why are we on\n\nTitle: Yoga"
    assert LLM_RESPONSE.exists()
