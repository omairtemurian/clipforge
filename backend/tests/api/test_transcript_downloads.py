"""Tests of the transcript (txt) and subtitle (srt, vtt) downloads of a
project's source and of a clip."""

import re
from pathlib import Path

import pytest
from apihelpers import assert_error
from clipforge.models import (
    CaptionCensor,
    CaptionMark,
    CaptionStyle,
    Segment,
    Transcript,
    Word,
)
from clipforge.pipeline.export import Cue
from clipforge.pipeline.transcript_files import format_cues, source_cues, vtt_time
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine

# One timing line of an SRT file and of a VTT file.
SRT_TIMING = re.compile(r"\d\d:\d\d:\d\d,\d{3} --> \d\d:\d\d:\d\d,\d{3}")
VTT_TIMING = re.compile(r"\d\d:\d\d:\d\d\.\d{3} --> \d\d:\d\d:\d\d\.\d{3}")


@pytest.fixture
def project(api_engine: Engine, sample_mp4: Path) -> int:
    """Add a project with a processed work directory; return its id."""
    project_id = add_project(api_engine)
    add_work(api_engine, project_id, sample_mp4)
    return project_id


def test_vtt_time_has_a_dot_before_the_milliseconds() -> None:
    assert vtt_time(61415) == "00:01:01.415"
    assert vtt_time(3_600_000 + 5) == "01:00:00.005"


def test_format_cues_writes_each_format() -> None:
    cues = [Cue(500, 1410, "Hi everyone."), Cue(61415, 62000, "a <b> & c")]

    assert format_cues(cues, "txt") == "Hi everyone.\na <b> & c\n"
    assert format_cues(cues, "srt") == (
        "1\n00:00:00,500 --> 00:00:01,410\nHi everyone.\n\n"
        "2\n00:01:01,415 --> 00:01:02,000\na <b> & c\n\n"
    )
    assert format_cues(cues, "vtt") == (
        "WEBVTT\n\n"
        "00:00:00.500 --> 00:00:01.410\nHi everyone.\n\n"
        "00:01:01.415 --> 00:01:02.000\na &lt;b&gt; &amp; c\n\n"
    )
    assert format_cues([], "vtt") == "WEBVTT\n\n"


def test_source_cues_skip_empty_and_instant_segments() -> None:
    def segment(start: float, end: float, text: str) -> Segment:
        word = Word(text="x", start=start, end=end, speaker="S0", prob=1.0)
        return Segment(
            id=0, start=start, end=end, text=text, words=[word], speaker="S0"
        )

    transcript = Transcript(
        language="en",
        duration=10,
        segments=[
            segment(0.5, 1.4, "  Hi \n there "),
            segment(2, 3, "   "),
            segment(4, 4, "instant"),
        ],
    )

    assert source_cues(transcript) == [Cue(500, 1400, "Hi there")]


def test_the_source_transcript_downloads_as_txt_srt_and_vtt(
    client: TestClient, project: int
) -> None:
    txt = client.get(f"/api/projects/{project}/transcript.txt")
    srt = client.get(f"/api/projects/{project}/transcript.srt")
    vtt = client.get(f"/api/projects/{project}/transcript.vtt")

    assert txt.status_code == srt.status_code == vtt.status_code == 200
    lines = txt.text.splitlines()
    assert len(lines) == 14
    assert lines[:2] == ["Hi everyone.", "So, I tried yoga."]
    assert txt.headers["content-type"] == "text/plain; charset=utf-8"
    assert (
        txt.headers["content-disposition"]
        == f'attachment; filename="clipforge-{project}-transcript.txt"'
    )

    assert srt.headers["content-type"].startswith("application/x-subrip")
    blocks = srt.text.rstrip("\n").split("\n\n")
    assert len(blocks) == 14
    assert blocks[0] == "1\n00:00:00,500 --> 00:00:01,410\nHi everyone."
    assert SRT_TIMING.fullmatch(blocks[13].splitlines()[1])

    assert vtt.headers["content-type"].startswith("text/vtt")
    assert vtt.text.startswith("WEBVTT\n\n00:00:00.500 --> 00:00:01.410\nHi everyone.")
    timings = [line for line in vtt.text.splitlines() if "-->" in line]
    assert len(timings) == 14
    assert all(VTT_TIMING.fullmatch(line) for line in timings)


def test_a_clip_downloads_its_captions_without_being_rendered(
    client: TestClient, api_engine: Engine, project: int
) -> None:
    clip_id = add_clip(api_engine, project, "candidate", 80, "Pizza night!")

    txt = client.get(f"/api/clips/{clip_id}/transcript.txt")
    srt = client.get(f"/api/clips/{clip_id}/transcript.srt")
    vtt = client.get(f"/api/clips/{clip_id}/transcript.vtt")

    assert txt.status_code == srt.status_code == vtt.status_code == 200
    # Clip 10-12.5 s: the words of segment 3 from 10 s on.
    assert txt.text.strip() != ""
    assert "Hi everyone" not in txt.text
    assert (
        txt.headers["content-disposition"]
        == f'attachment; filename="{clip_id}-pizza-night.txt"'
    )
    cues = [b for b in srt.text.rstrip("\n").split("\n\n")]
    assert [c.splitlines()[0] for c in cues] == [
        str(n) for n in range(1, len(cues) + 1)
    ]
    assert all(SRT_TIMING.fullmatch(c.splitlines()[1]) for c in cues)
    assert srt.text.startswith("1\n00:00:00,")
    assert vtt.text.startswith("WEBVTT\n\n00:00:00.")
    assert len(txt.text.splitlines()) == len(cues)
    # Same cues in all three formats.
    assert [
        line.replace(".", ",") for line in vtt.text.splitlines() if "-->" in line
    ] == [c.splitlines()[1] for c in cues]


def test_a_clips_files_have_its_edits_and_masked_censored_words(
    client: TestClient, api_engine: Engine, project: int
) -> None:
    plain = add_clip(api_engine, project, "candidate", 80)
    marked = add_clip(
        api_engine,
        project,
        "candidate",
        80,
        caption_style=CaptionStyle(
            censor=CaptionCensor(auto=False),
            word_marks=[CaptionMark(start=11.1, censor=True)],
        ),
    )

    before = client.get(f"/api/clips/{plain}/transcript.txt").text
    after = client.get(f"/api/clips/{marked}/transcript.txt").text

    assert before != after
    assert "*" in after
    assert "*" not in before


def test_downloads_need_a_processed_project_and_a_known_format(
    client: TestClient, api_engine: Engine, project: int
) -> None:
    clip_id = add_clip(api_engine, project, "candidate", 80)
    bare = add_project(api_engine)
    bare_clip = add_clip(api_engine, bare, "candidate", 80)

    assert_error(client.get("/api/projects/999/transcript.txt"), 404, "not_found")
    assert_error(client.get("/api/clips/999/transcript.txt"), 404, "not_found")
    assert_error(client.get(f"/api/projects/{bare}/transcript.txt"), 409, "conflict")
    assert_error(client.get(f"/api/clips/{bare_clip}/transcript.srt"), 409, "conflict")
    assert_error(
        client.get(f"/api/clips/{clip_id}/transcript.docx"), 422, "validation_error"
    )
