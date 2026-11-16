"""Tests of auto sound effects (SPEC-v2 3.5, pipeline/sfx): the bundled pack
and its licenses, the tag search, the moments of a clip numbered for the
LLM (mocked), its picks checked and sent back with their errors, where the
sounds are placed, and a render whose silent gap gets a bundled sound."""

import json
import re
from pathlib import Path

import pytest
from builders import make_clip, said
from clipforge.config import RenderSettings
from clipforge.ffmpeg import ffprobe_json, run_ffmpeg
from clipforge.hooks_templates import SFX_DIR as HOOK_SFX_DIR
from clipforge.models import AudioProps, FaceBox, SfxPick, TrackItem
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.polish import spoken_words
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import render_clip
from clipforge.pipeline.sfx import (
    AUTO_ID,
    BUNDLED_SFX,
    SFX_DIR,
    SFX_LICENSE,
    SFX_VOLUME,
    Moment,
    SfxError,
    bundled_sfx,
    clip_joins,
    clip_moments,
    find_sfx,
    merge_sfx,
    pack_tags,
    place_sfx,
    search_sfx,
    sfx_items,
    system_prompt,
    user_prompt,
)
from clipforge.pipeline.timeline_graph import Layer
from fakes import FakeLLMClient

FPS = 30
# "He said it. And then, boom: a joke."
JOKE = said(
    ("He", 1.0, 1.2),
    (" said", 1.3, 1.6),
    (" it.", 1.7, 2.0),
    (" And", 4.0, 4.2),
    (" then,", 4.3, 4.6),
    (" boom:", 4.7, 5.0),
    (" a", 5.1, 5.2),
    (" joke.", 5.3, 5.8),
)
JOKE_CLIP = make_clip("karaoke_bold", start=1.0, end=6.0)


def reply(*picks: tuple[int, list[str]]) -> str:
    """Return an LLM reply with the sounds picks (moment, tags)."""
    return json.dumps({"sounds": [{"moment": m, "tags": t} for m, t in picks]})


def moments_of(clip_changes: dict[str, object] | None = None) -> list[Moment]:
    """Return the moments of JOKE_CLIP with changes."""
    clip = JOKE_CLIP.model_copy(update=clip_changes or {})
    return clip_moments(spoken_words(JOKE, clip, FPS), clip_joins(clip, FPS))


def test_every_sound_of_the_pack_has_its_file_license_and_length() -> None:
    licenses = (SFX_DIR / "LICENSES.md").read_text()
    files = sorted(path.name for path in SFX_DIR.glob("*.flac"))

    assert files == sorted(sound.file for sound in BUNDLED_SFX)
    assert SFX_DIR == HOOK_SFX_DIR and SFX_LICENSE == "CC0-1.0"
    assert "CC0 1.0" in licenses
    for sound in BUNDLED_SFX:
        assert f"`{sound.file}` | {sound.title} |" in licenses
        assert sound.title in sound.attribution and SFX_LICENSE in sound.attribution
        assert sound.tags == tuple(tag.lower() for tag in sound.tags)
        info = ffprobe_json(SFX_DIR / sound.file)
        assert info["streams"][0]["codec_name"] == "flac"
        assert float(info["format"]["duration"]) == pytest.approx(sound.seconds, 0.02)
        assert bundled_sfx(Path("/elsewhere") / sound.file) == sound
    assert bundled_sfx("other.flac") is None


def test_the_pack_covers_cuts_punchlines_and_emphasis() -> None:
    tags = pack_tags()

    assert tags == sorted(set(tags))
    assert {"whoosh", "cut", "punchline", "laugh", "emphasis", "pop"} <= set(tags)


def test_search_finds_the_sound_with_most_tags() -> None:
    assert search_sfx(["whoosh", "fast"]) == bundled_sfx("whoosh_swift.flac")
    assert search_sfx(["Whoosh", " SOFT "]) == bundled_sfx("whoosh_soft.flac")
    assert search_sfx(["punchline", "laugh"]) == bundled_sfx("crowd_laugh.flac")
    assert search_sfx(["punchline", "drums"]) == bundled_sfx("rimshot_badum.flac")
    assert search_sfx(["whoosh"]) == bundled_sfx("whoosh_swift.flac")
    assert search_sfx(["no such tag"]) is None
    assert search_sfx([]) is None


def test_search_avoids_sounds_that_are_used_if_another_fits() -> None:
    swift, soft = bundled_sfx("whoosh_swift.flac"), bundled_sfx("whoosh_soft.flac")
    assert swift is not None and soft is not None

    assert search_sfx(["whoosh"], avoid=[swift]) == soft
    assert search_sfx(["fast"], avoid=[swift]) == swift
    assert search_sfx(["whoosh"], avoid=[swift, soft]) == swift


def test_the_moments_are_the_cuts_and_the_words_in_time_order() -> None:
    cut = {"cut_ranges": [(2.0, 4.0)]}

    moments = moments_of(cut)

    assert [(m.kind, m.text) for m in moments] == [
        ("word", "He"),
        ("word", "said"),
        ("word", "it."),
        ("cut", ""),
        ("word", "And"),
        ("word", "then,"),
        ("word", "boom:"),
        ("word", "a"),
        ("word", "joke."),
    ]
    assert moments[3].time == pytest.approx(1.0)
    assert moments[4].time == pytest.approx(1.0)
    assert [m.time for m in moments] == sorted(m.time for m in moments)


def test_sections_apart_in_the_source_join_and_neighbours_do_not() -> None:
    apart = JOKE_CLIP.model_copy(update={"segments": [(1.0, 2.0), (4.0, 6.0)]})
    touching = JOKE_CLIP.model_copy(update={"segments": [(1.0, 2.0), (2.0, 6.0)]})

    assert clip_joins(apart, FPS) == [pytest.approx(1.0)]
    assert clip_joins(touching, FPS) == []
    assert clip_joins(JOKE_CLIP, FPS) == []
    assert clip_joins(JOKE_CLIP.model_copy(update={"cut_ranges": [(2, 3)]}), FPS) == [
        pytest.approx(1.0)
    ]


def test_the_prompt_numbers_the_moments_and_lists_the_pack_tags() -> None:
    moments = moments_of({"cut_ranges": [(2.0, 4.0)]})

    user = user_prompt(moments)
    system = system_prompt(4)

    assert user.splitlines()[:3] == [
        "The moments of the clip:",
        "0: 0.00s He",
        "1: 0.30s said",
    ]
    assert "3: cut at 1.00s" in user
    assert '"sounds"' in system and "no more than 4" in system
    assert "punchline" in system and "whoosh" in system
    assert "at least 2 seconds apart" in system
    assert "$tags" not in system and "$max_items" not in system


def test_the_llm_picks_the_sounds_and_they_come_in_time_order() -> None:
    moments = moments_of()
    llm = FakeLLMClient(reply((7, ["punchline", "laugh"]), (1, ["emphasis", "pop"])))

    picks = find_sfx(llm, moments, 5, 7)

    assert picks == [
        SfxPick(moment=1, tags=["emphasis", "pop"]),
        SfxPick(moment=7, tags=["punchline", "laugh"]),
    ]
    [(system, user)] = llm.calls
    assert "sound effects" in system
    assert "7: 4.30s joke." in user


def test_invalid_replies_are_sent_back_with_their_errors() -> None:
    moments = moments_of()
    llm = FakeLLMClient(
        "not json",
        reply((99, ["pop"]), (3, ["nope"]), (2, ["pop"]), (2, ["ding"])),
        reply((7, ["laugh"])),
    )

    picks = find_sfx(llm, moments, 5, 7)

    assert picks == [SfxPick(moment=7, tags=["laugh"])]
    assert len(llm.calls) == 3
    errors = llm.calls[2][1]
    assert "sounds.0: moment 99 does not exist" in errors
    assert "sounds.1: no sound has the tags ['nope']" in errors
    assert "sounds.3: moment 2 is picked twice" in errors


def test_after_the_last_try_the_usable_picks_are_kept() -> None:
    moments = moments_of()
    bad = reply((1, ["pop"]), (2, ["pop"]), (7, ["laugh"]))
    llm = FakeLLMClient(bad, repeat_last=True)

    picks = find_sfx(llm, moments, 1, 7)

    assert [pick.moment for pick in picks] == [1]
    assert len(llm.calls) == 3
    assert "sounds.1: moment 2 is too close to another" in llm.calls[1][1]
    assert "sounds.2: more than 1 sounds" in llm.calls[1][1]


def test_no_valid_reply_is_an_error_and_no_moments_ask_nothing() -> None:
    with pytest.raises(SfxError, match="3 tries"):
        find_sfx(FakeLLMClient("{}", repeat_last=True), moments_of(), 5, 7)
    llm = FakeLLMClient()

    assert find_sfx(llm, [], 5, 7) == []
    assert llm.calls == []


def test_a_clip_that_needs_no_sound_gets_none() -> None:
    llm = FakeLLMClient(reply())

    assert find_sfx(llm, moments_of(), 5, 7) == []
    assert place_sfx([], moments_of(), 5.0) == []


def test_a_sound_on_a_cut_is_centred_on_it_and_on_a_word_starts_with_it() -> None:
    moments = moments_of({"cut_ranges": [(2.0, 4.0)]})
    picks = [
        SfxPick(moment=3, tags=["whoosh", "soft"]),
        SfxPick(moment=8, tags=["punchline", "laugh"]),
    ]

    [cut, word] = place_sfx(picks, moments, 3.0)

    assert (cut.sound.file, cut.start, cut.end) == ("whoosh_soft.flac", 0.6, 1.5)
    assert cut.moment.kind == "cut"
    assert (word.sound.file, word.start) == ("crowd_laugh.flac", 2.3)
    assert word.end == 3.0


def test_sounds_that_repeat_a_tag_differ_while_the_pack_has_another() -> None:
    moments = moments_of({"cut_ranges": [(2.0, 4.0)]})
    picks = [SfxPick(moment=m, tags=["whoosh"]) for m in (3, 8)]

    placed = place_sfx(picks, moments, 3.0)

    assert [p.sound.file for p in placed] == ["whoosh_swift.flac", "whoosh_soft.flac"]


def test_a_sound_that_would_be_left_with_no_length_is_dropped() -> None:
    moments = [Moment(0.0, "word", "a"), Moment(3.98, "word", "b")]
    picks = [SfxPick(moment=0, tags=["pop"]), SfxPick(moment=1, tags=["pop"])]

    placed = place_sfx(picks, moments, 4.0)

    assert [(p.start, p.end) for p in placed] == [(0.0, 0.15)]


def test_items_play_the_library_asset_and_replace_the_earlier_auto_items() -> None:
    moments = moments_of()
    placements = place_sfx(
        [SfxPick(moment=3, tags=["pop"]), SfxPick(moment=7, tags=["laugh"])],
        moments,
        5.0,
    )
    ids = {"pop_bubble.flac": 11, "crowd_laugh.flac": 12}

    items = sfx_items(placements, ids)
    own = TrackItem(id="mine", kind="audio", asset_id=5, start=0.1, end=0.5)
    old = TrackItem(id=f"{AUTO_ID}-9", kind="audio", asset_id=11, start=0, end=1)
    track = merge_sfx([old, own], items)

    assert [(i.id, i.asset_id, i.kind) for i in items] == [
        (f"{AUTO_ID}-1", 11, "audio"),
        (f"{AUTO_ID}-2", 12, "audio"),
    ]
    assert items[0].props == {"volume": SFX_VOLUME}
    assert AudioProps.model_validate(items[0].props).volume == SFX_VOLUME
    assert [i.id for i in track] == ["mine", f"{AUTO_ID}-1", f"{AUTO_ID}-2"]
    assert sfx_items(placements, {"pop_bubble.flac": 11}) == items[:1]


def rms_db(path: Path, start: float, length: float) -> float:
    """Return the RMS level in dBFS of path's sound from start for length
    seconds, as astats measures it."""
    stderr = run_ffmpeg(
        ["-ss", f"{start}", "-t", f"{length}", "-i", path, "-map", "0:a:0"]
        + ["-af", "astats=measure_perchannel=none:measure_overall=RMS_level"]
        + ["-f", "null", "-"],
        loglevel="info",
    ).stderr.decode()
    return float(re.findall(r"RMS level dB: (\S+)", stderr)[-1])


def test_a_bundled_sound_is_heard_in_the_render_where_it_was_placed(
    tmp_path: Path, sample_mp4: Path
) -> None:
    # The fixture is silent from 2.89 to 3.46 s: a sound placed there is
    # all that the render has to say in that window.
    faces: list[list[FaceBox]] = [[] for _ in sample_times(0.0, 6.0)]
    plan = plan_crop(ClipSpan(7, 0.0, 6.0), "9:16", (320, 240), faces, [])
    sound = bundled_sfx("impact_boom.flac")
    assert sound is not None
    item = TrackItem(id="auto-sfx-1", kind="audio", asset_id=1, start=2.9, end=4.1)

    def render(name: str, layers: list[Layer]) -> Path:
        return render_clip(
            sample_mp4,
            tmp_path / name,
            0.0,
            6.0,
            plan,
            "fill",
            RenderSettings(),
            size=(180, 320),
            layers=layers,
        )

    plain = render("plain.mp4", [])
    with_sound = render(
        "sfx.mp4",
        [Layer("sfx", item, AudioProps(volume=SFX_VOLUME), SFX_DIR / sound.file)],
    )

    assert rms_db(plain, 2.95, 0.4) < -50
    assert rms_db(with_sound, 2.95, 0.4) > -30
