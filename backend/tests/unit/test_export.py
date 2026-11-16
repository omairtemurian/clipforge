"""Tests of pipeline/export (SPEC 6.12): SRT subtitles in the exact SubRip
format, which ffmpeg reads and writes unchanged, with the words of a clip's
render after its cuts; the metadata JSON with its credit line; zip archives."""

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from builders import SIX, make_clip, source_meta, word
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import Clip, SourceMeta, Transcript
from clipforge.pipeline.caption_lines import CaptionWord
from clipforge.pipeline.export import (
    build_srt,
    credit_line,
    srt_time,
    write_metadata,
    write_srt,
    write_zip,
)
from clipforge.pipeline.step import META, TRANSCRIPT, StepError, write_json

# The words of builders.SIX in milliseconds from the clip's start, 10 s.
WORDS = [
    CaptionWord("Wait,", 0, 300),
    CaptionWord("my", 360, 500),
    CaptionWord("brother", 540, 800),
    CaptionWord("ate", 840, 1100),
    CaptionWord("the", 1140, 1250),
    CaptionWord("pizza.", 1700, 2200),
]
# In lines of 3 words at most (karaoke_bold): "Wait," ends a line with its
# comma and the pause before "pizza." ends another. Each line shows until the
# next one starts, but "the" only until its end, as the pause follows it.
SRT_3 = """\
1
00:00:00,000 --> 00:00:00,360
Wait,

2
00:00:00,360 --> 00:00:01,140
my brother ate

3
00:00:01,140 --> 00:00:01,250
the

4
00:00:01,700 --> 00:00:02,200
pizza.

"""
# In lines of 4 words at most (minimal).
SRT_4 = """\
1
00:00:00,000 --> 00:00:00,360
Wait,

2
00:00:00,360 --> 00:00:01,250
my brother ate the

3
00:00:01,700 --> 00:00:02,200
pizza.

"""
# The meta.json of a downloaded video, and of a local file (no channel).
DOWNLOADED = source_meta().model_copy(
    update={
        "title": "Best of Sample Comedian",
        "channel": "Sample Comedian",
        "channel_url": "https://www.youtube.com/@SampleComedian",
    }
)
LOCAL = source_meta()


def rendered(tmp_path: Path, **changes: Any) -> Clip:
    """Return clip 7 (make_clip with karaoke_bold and changes), rendered to
    tmp_path/output/7.mp4."""
    video = tmp_path / "output" / "7.mp4"
    video.parent.mkdir(exist_ok=True)
    fields = {"status": "rendered", "output_path": str(video)} | changes
    return make_clip("karaoke_bold", **fields)


@pytest.mark.parametrize(
    ("time", "text"),
    [
        (0, "00:00:00,000"),
        (61415, "00:01:01,415"),
        (3723004, "01:02:03,004"),
        (359999999, "99:59:59,999"),
    ],
)
def test_srt_time_has_hours_minutes_seconds_and_milliseconds(
    time: int, text: str
) -> None:
    assert srt_time(time) == text


def test_build_srt_has_a_numbered_cue_for_each_caption_line() -> None:
    assert build_srt(WORDS, 3) == SRT_3
    assert build_srt(WORDS, 4) == SRT_4


def test_build_srt_skips_empty_lines_and_keeps_text_on_one_line() -> None:
    words = [
        CaptionWord("Oh.", 500, 500),
        CaptionWord("two\n\nlines", 2000, 2400),
        CaptionWord("here", 2450, 2900),
    ]

    assert build_srt(words, 3) == "1\n00:00:02,000 --> 00:00:02,900\ntwo lines here\n\n"
    assert build_srt([], 3) == ""


def test_ffmpeg_reads_and_writes_the_subtitles_unchanged(tmp_path: Path) -> None:
    words = [*WORDS, CaptionWord("café", 2300, 2600), CaptionWord("🍕", 2650, 2900)]
    ours, theirs = tmp_path / "ours.srt", tmp_path / "theirs.srt"
    ours.write_text(build_srt(words, 3), encoding="utf-8")

    run_ffmpeg(["-i", ours, theirs])

    assert theirs.read_bytes() == ours.read_bytes()
    assert ours.read_text(encoding="utf-8").endswith(
        "5\n00:00:02,300 --> 00:00:02,900\ncafé 🍕\n\n"
    )


def test_write_srt_has_the_words_of_the_render_after_its_cuts(tmp_path: Path) -> None:
    transcript = Transcript(language="en", duration=60, segments=[SIX])
    write_json(tmp_path / TRANSCRIPT, transcript)
    # At 30 fps the cut runs from frame 10 to 25 of the clip (0.333-0.833 s),
    # which leaves out "my brother"; "pizza." is edited.
    clip = rendered(
        tmp_path,
        cut_ranges=[(10.33, 10.82)],
        caption_overrides=[word("pizza!", 11.7, 12.2)],
    )

    path = write_srt(tmp_path, clip, 30)

    assert path == tmp_path / "output" / "7.srt"
    assert path.read_text(encoding="utf-8") == (
        "1\n00:00:00,000 --> 00:00:00,340\nWait,\n\n"
        "2\n00:00:00,340 --> 00:00:00,750\nate the\n\n"
        "3\n00:00:01,200 --> 00:00:01,700\npizza!\n\n"
    )
    assert write_srt(tmp_path, rendered(tmp_path), 30).read_text() == SRT_3


def test_write_srt_needs_a_rendered_clip_and_the_transcript(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="clip 7 has no rendered video"):
        write_srt(tmp_path, make_clip("karaoke_bold"), 30)
    with pytest.raises(StepError, match="transcript.json not found"):
        write_srt(tmp_path, rendered(tmp_path), 30)
    assert list((tmp_path / "output").iterdir()) == []


@pytest.mark.parametrize(
    ("template", "meta", "line"),
    [
        ("Credit: {channel}", DOWNLOADED, "Credit: Sample Comedian"),
        (
            "Credit: {channel} — {channel_url}",
            DOWNLOADED,
            "Credit: Sample Comedian — https://www.youtube.com/@SampleComedian",
        ),
        (
            "From {title} {{full video}}",
            DOWNLOADED,
            "From Best of Sample Comedian {full video}",
        ),
        ("Credit: {channel}", LOCAL, None),
        ("Clipped from {title} ", LOCAL, "Clipped from sample"),
        ("Clipped with ClipForge", LOCAL, "Clipped with ClipForge"),
        (" ", DOWNLOADED, None),
    ],
)
def test_credit_line_fills_the_template_with_the_source(
    template: str, meta: SourceMeta, line: str | None
) -> None:
    assert credit_line(template, meta) == line


def test_credit_line_rejects_other_fields() -> None:
    with pytest.raises(ValueError, match="credit_template may only use"):
        credit_line("Credit: {uploader}", DOWNLOADED)


def test_write_metadata_has_the_clip_text_and_the_credit(tmp_path: Path) -> None:
    write_json(tmp_path / META, DOWNLOADED)
    clip = rendered(tmp_path, title="Pizza — 🍕", description="He ate it all.")

    path = write_metadata(tmp_path, clip, "Credit: {channel} — {channel_url}")

    assert path == tmp_path / "output" / "7.json"
    text = path.read_text(encoding="utf-8")
    assert json.loads(text) == {
        "title": "Pizza — 🍕",
        "description": "He ate it all.",
        "hashtags": ["food", "pizza", "funny"],
        "credit": "Credit: Sample Comedian — https://www.youtube.com/@SampleComedian",
    }
    assert list(json.loads(text)) == ["title", "description", "hashtags", "credit"]
    assert '  "title": "Pizza — 🍕",\n' in text and text.endswith("}\n")

    write_json(tmp_path / META, LOCAL)
    local = json.loads(write_metadata(tmp_path, clip, "Credit: {channel}").read_text())
    assert local["credit"] is None


def test_write_metadata_needs_a_rendered_clip_and_meta(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="clip 7 has no rendered video"):
        write_metadata(tmp_path, make_clip("karaoke_bold"), "Credit: {channel}")
    with pytest.raises(StepError, match="meta.json not found; run the ingest"):
        write_metadata(tmp_path, rendered(tmp_path), "Credit: {channel}")


def test_write_zip_stores_videos_and_deflates_the_rest(tmp_path: Path) -> None:
    files = [tmp_path / name for name in ("7.mp4", "7.srt", "7.json")]
    for file in files:
        file.write_bytes(f"data of {file.name}\n".encode() * 50)
    path = tmp_path / "zips" / "clips.zip"

    assert write_zip(path, files) == path

    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        assert [(i.filename, i.compress_type) for i in archive.infolist()] == [
            ("7.mp4", zipfile.ZIP_STORED),
            ("7.srt", zipfile.ZIP_DEFLATED),
            ("7.json", zipfile.ZIP_DEFLATED),
        ]
        assert [archive.read(file.name) for file in files] == [
            file.read_bytes() for file in files
        ]
    assert list(path.parent.iterdir()) == [path]


def test_write_zip_of_a_missing_file_leaves_no_archive(tmp_path: Path) -> None:
    video = tmp_path / "7.mp4"
    video.write_bytes(b"video")

    with pytest.raises(FileNotFoundError):
        write_zip(tmp_path / "clips.zip", [video, tmp_path / "7.srt"])
    assert list(tmp_path.iterdir()) == [video]
