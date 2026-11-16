"""Tests of the auto censor (SPEC-v2 3.4, pipeline/censor): the default and
custom lists matched in any case, per-word marks, masked caption text and
the windows and filters of the censored sound."""

from pathlib import Path

import pytest
from builders import make_clip, said
from clipforge.captions_templates import get_template
from clipforge.models import CaptionCensor, CaptionMark, CaptionStyle, CensorWords
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.captions import write_captions
from clipforge.pipeline.censor import (
    censor_filter,
    censor_windows,
    compile_entries,
    default_entries,
    load_custom,
    load_matcher,
    mask,
    save_custom,
)
from clipforge.pipeline.export import write_srt
from clipforge.pipeline.polish import rendered_words
from clipforge.pipeline.step import TRANSCRIPT, StepError, write_json
from pydantic import ValidationError

# Clip 7 (10-12.5 s) says "Holy shit, yoga is FUCKING hard."
WORDS = said(
    ("Holy", 10.0, 10.3),
    ("shit,", 10.4, 10.8),
    ("yoga", 10.9, 11.2),
    ("is", 11.25, 11.4),
    ("FUCKING", 11.45, 11.9),
    ("hard.", 11.95, 12.3),
)
AUTO = CaptionCensor()


def texts(words: list[CaptionWord]) -> list[str]:
    return [word.text for word in words]


def censored_clip(
    censor: CaptionCensor | None = AUTO, marks: list[CaptionMark] | None = None
) -> list[CaptionWord]:
    """Return the rendered words of clip 7 of WORDS with censor and marks."""
    style = CaptionStyle(censor=censor, word_marks=marks)
    return rendered_words(WORDS, make_clip("minimal", caption_style=style), 30)


def test_the_default_list_matches_any_case_and_prefixes() -> None:
    matcher = compile_entries(default_entries("en"))

    assert matcher.matches("Shit,") and matcher.matches("FUCKING")
    assert matcher.matches("motherfucker!") and matcher.matches("fuckin'")
    assert not matcher.matches("yoga") and not matcher.matches("assume")
    assert not matcher.matches("...")


def test_another_language_adds_its_list_to_english(tmp_path: Path) -> None:
    (tmp_path / "censor_en.txt").write_text("# comment\nshit\n")
    (tmp_path / "censor_es.txt").write_text("mierda*\n\n")

    assert default_entries("es", tmp_path) == ("shit", "mierda*")
    assert default_entries("de", tmp_path) == ("shit",)


def test_the_custom_list_adds_to_the_default_in_any_case(data_dir: Path) -> None:
    assert load_custom() == CensorWords()
    save_custom(CensorWords(words=["Yoga", "HARD*", "yoga"]))

    assert load_custom().words == ["yoga", "hard*"]
    matcher = load_matcher("en")
    assert matcher.matches("YOGA.") and matcher.matches("Hardest")
    assert matcher.matches("shit")


def test_a_custom_entry_is_one_word() -> None:
    for entry in ("two words", "*", "", "a*b"):
        with pytest.raises(ValidationError):
            CensorWords(words=[entry])


def test_a_broken_custom_list_is_a_step_error(data_dir: Path) -> None:
    data_dir.mkdir()
    (data_dir / "censor_words.json").write_text("{")

    with pytest.raises(StepError, match="not a valid censor list"):
        load_matcher("en")


def test_mask_keeps_the_first_letter_and_the_punctuation() -> None:
    assert mask("fuck") == "f***"
    assert mask("Shit,") == "S***,"
    assert mask("'bitch'") == "'b****'"
    assert mask("...") == "..."


def test_auto_censor_masks_the_listed_words(data_dir: Path) -> None:
    assert texts(censored_clip()) == [
        "Holy",
        "s***,",
        "yoga",
        "is",
        "F******",
        "hard.",
    ]


def test_without_auto_censor_nothing_is_masked(data_dir: Path) -> None:
    assert texts(censored_clip(None))[1] == "shit,"
    assert texts(censored_clip(CaptionCensor(auto=False)))[1] == "shit,"


def test_a_mark_censors_or_spares_one_word(data_dir: Path) -> None:
    marks = [
        CaptionMark(start=10.9, censor=True),
        CaptionMark(start=10.4, censor=False),
    ]

    assert texts(censored_clip(AUTO, marks))[1:3] == ["shit,", "y***"]
    assert texts(censored_clip(None, marks))[1:5] == ["shit,", "y***", "is", "FUCKING"]


def test_captions_and_subtitles_show_the_masked_words(
    data_dir: Path, tmp_path: Path
) -> None:
    write_json(tmp_path / TRANSCRIPT, WORDS)
    clip = make_clip("minimal", caption_style=CaptionStyle(censor=AUTO))

    ass = write_captions(tmp_path, clip, (1080, 1920), 30).read_text()
    video = tmp_path / "7.mp4"
    srt = write_srt(tmp_path, clip.model_copy(update={"output_path": str(video)}), 30)

    for text in (ass, srt.read_text()):
        assert "s***" in text and "F******" in text
        assert "shit" not in text and "FUCKING" not in text


def test_the_windows_pad_and_merge_the_censored_words(data_dir: Path) -> None:
    words = [
        CaptionWord("shit", 400, 800),
        CaptionWord("fuck", 820, 1000),
        CaptionWord("ok", 1100, 1300),
        CaptionWord("bitch", 0, 30),
    ]

    windows = censor_windows(words, AUTO, "en")

    assert windows == [(0.0, 0.08), (0.35, 1.05)]


def test_the_filters_beep_or_mute_inside_the_windows() -> None:
    windows = [(0.35, 1.05), (2.0, 2.5)]
    enable = "enable='between(t,0.350,1.050)+between(t,2.000,2.500)'"

    assert censor_filter(windows, "mute") == f"volume=volume=0:{enable}"
    assert censor_filter(windows, "beep") == (
        f"aeval=exprs=0.3*sin(2*PI*1000*t):c=same:{enable}"
    )
    assert censor_filter([], "beep") == ""


def test_censor_belongs_to_the_clip_not_to_its_template() -> None:
    template = get_template("minimal")

    assert template.styled(CaptionStyle(censor=AUTO)) == template
