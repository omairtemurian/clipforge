"""Tests of reading an uploaded SRT or VTT file (pipeline.subtitle_import)."""

from pathlib import Path

import pytest
from clipforge.config import Settings
from clipforge.pipeline.subtitle_import import (
    MAX_SUBTITLE_BYTES,
    Cue,
    SubtitlesError,
    cue_words,
    parse_subtitles,
    save_subtitles,
    subtitles_path,
)

SRT = """\ufeff1
00:00:02,000 --> 00:00:04,500
<i>Hello</i> there,
{\\an8}friend.

2
00:00:05.000 --> 00:00:06,000
Bye

3
00:00:07,000 --> 00:00:08,000
   
"""


def test_parse_subtitles_reads_cues_without_tags_or_blank_ones() -> None:
    assert parse_subtitles(SRT) == [
        Cue(2.0, 4.5, "Hello there, friend."),
        Cue(5.0, 6.0, "Bye"),
    ]


def test_parse_subtitles_sorts_cues_and_needs_no_counters() -> None:
    text = (
        "01:00:00,000 --> 01:00:01,000\nlate\n\n00:00:01,000 --> 00:00:02,000\nearly\n"
    )

    assert [cue.text for cue in parse_subtitles(text)] == ["early", "late"]
    assert parse_subtitles(text)[1].start == 3600.0


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("", "^the file has no subtitle cues"),
        ("just some text\n", "^line 1: expected a cue number"),
        ("00:00:03,000 --> 00:00:01,000\nback\n", "^line 1: .*ends before"),
        ("1\n00:00:01,000 --> soon\nhi\n", "^line 2: cannot read the timing"),
        ("1\n00:00:01,000 --> 00:00:02,000\nhi\n\n2\n\n", "^line 5: .*no timing"),
        ("1\n2\n00:00:01,000 --> 00:00:02,000\nhi\n", "^line 2: expected a timing"),
        ("WEBVTT\n\ncue\n", "^line 3: the cue has no timing"),
        ("WEBVTT\n\nNOTE only\n", "^the file has no subtitle cues"),
    ],
)
def test_parse_subtitles_rejects_files_without_valid_cues(
    text: str, error: str
) -> None:
    with pytest.raises(SubtitlesError, match=error):
        parse_subtitles(text)


def test_cue_words_share_a_cue_by_word_length() -> None:
    words = cue_words([Cue(10.0, 12.0, "a bbb"), Cue(20.0, 21.0, "late")], 0, 15)

    assert [(w.text, w.start, w.end, w.segment_end) for w in words] == [
        (" a", 10.0, 10.667, False),
        (" bbb", 10.667, 12.0, True),
    ]
    assert {w.prob for w in words} == {1.0}
    assert all(w.approximate for w in words)


def test_cue_words_keep_cues_that_overlap_the_timeframe() -> None:
    cues = [Cue(0.0, 2.0, "before"), Cue(4.0, 6.0, "edge"), Cue(9.0, 11.0, "after")]

    assert [w.text for w in cue_words(cues, 5.0, 9.0)] == [" edge"]


def test_save_subtitles_saves_valid_srt_under_a_random_token(tmp_path: Path) -> None:
    cfg = Settings(data_dir=tmp_path)

    token = save_subtitles(SRT.encode("utf-8"), cfg)

    assert len(token) == 32 and int(token, 16) >= 0
    assert subtitles_path(token, cfg) == tmp_path / "subtitles" / f"{token}.srt"
    assert parse_subtitles(
        subtitles_path(token, cfg).read_text("utf-8")
    ) == parse_subtitles(SRT)
    assert save_subtitles(SRT.encode("utf-8"), cfg) != token


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"\xff\xfe1\n", "not UTF-8"),
        (b"x" * (MAX_SUBTITLE_BYTES + 1), "larger than"),
        (b"no cues here", "^line 1: expected a cue number"),
    ],
)
def test_save_subtitles_rejects_files_that_are_not_subtitles(
    data: bytes, error: str, tmp_path: Path
) -> None:
    with pytest.raises(SubtitlesError, match=error):
        save_subtitles(data, Settings(data_dir=tmp_path))
    assert not (tmp_path / "subtitles").exists()


VTT = """\ufeffWEBVTT - a talk
Kind: captions

NOTE a comment
that spans lines

STYLE
::cue { color: red }

intro
00:02.000 --> 00:04.500 line:85% align:start
<v Ann>Hello <00:00:03.000>there,</v>
&amp; <c.loud>friend</c>

00:00:05.250 --> 00:00:06.000
Bye

00:00:07.000 --> 00:00:08.000
"""


def test_parse_subtitles_reads_webvtt_without_header_notes_or_settings() -> None:
    assert parse_subtitles(VTT) == [
        Cue(2.0, 4.5, "Hello there, & friend"),
        Cue(5.25, 6.0, "Bye"),
    ]


def test_parse_subtitles_takes_a_fraction_as_its_digits() -> None:
    [cue] = parse_subtitles("00:00:01,5 --> 00:00:02.25\nhi\n")

    assert (cue.start, cue.end) == (1.5, 2.25)


def test_parse_subtitles_needs_no_blank_line_between_srt_cues() -> None:
    text = (
        "1\n00:00:01,000 --> 00:00:02,000\nfirst\n"
        "2\n00:00:03,000 --> 00:00:04,000\nsecond\n"
    )

    assert [cue.text for cue in parse_subtitles(text)] == ["first", "second"]


def test_save_subtitles_saves_webvtt_too(tmp_path: Path) -> None:
    cfg = Settings(data_dir=tmp_path)

    token = save_subtitles(VTT.encode("utf-8"), cfg)

    assert parse_subtitles(subtitles_path(token, cfg).read_text("utf-8")) == (
        parse_subtitles(VTT)
    )
