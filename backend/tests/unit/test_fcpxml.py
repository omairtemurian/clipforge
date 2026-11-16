"""Tests of the Premiere export (SPEC 6.12, 9.2): Final Cut Pro 7 XML (xmeml
version 4) with a sequence for each clip that plays its frames of the source,
and clips.export_premiere."""

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from builders import make_clip, source_meta
from clipforge.clips import PREMIERE_NAME, export_premiere
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import Clip
from clipforge.pipeline.premiere import (
    FILE_ID,
    PROLOGUE,
    Rate,
    Source,
    build_xmeml,
    path_url,
    xml_rate,
)
from clipforge.pipeline.step import META, SOURCE, StepError, write_json
from seed import add_clip, add_project
from sqlalchemy import Engine

LINK_TAGS = ("linkclipref", "mediatype", "trackindex", "clipindex", "groupindex")


def source(channels: int = 2, fps: float = 30.0, duration: float = 60.0) -> Source:
    """Return job 7's source.mp4: a 1280x720 video called "sample" that lasts
    duration seconds at fps, with 48 kHz audio of channels channels."""
    meta = source_meta(end=duration).model_copy(update={"fps": fps})
    return Source(Path("/data/work/7") / SOURCE, meta, 48000, channels)


def sequences(clips: list[Clip], src: Source) -> list[ET.Element]:
    """Return the sequences of build_xmeml's document of clips on src."""
    return ET.fromstring(build_xmeml(clips, src)).findall("project/children/sequence")


def clipitems(sequence: ET.Element) -> list[ET.Element]:
    """Return the clipitems of sequence: its video one, then its audio ones."""
    return sequence.findall("media/*/track/clipitem")


def frames(item: ET.Element) -> tuple[str | None, ...]:
    """Return the in, out, start and end frames of the clipitem item."""
    return tuple(item.findtext(tag) for tag in ("in", "out", "start", "end"))


@pytest.mark.parametrize(
    ("fps", "rate"),
    [
        (24000 / 1001, Rate(24, ntsc=True)),
        (23.976, Rate(24, ntsc=True)),
        (24.0, Rate(24, ntsc=False)),
        (25.0, Rate(25, ntsc=False)),
        (30000 / 1001, Rate(30, ntsc=True)),
        (29.97, Rate(30, ntsc=True)),
        (30.0, Rate(30, ntsc=False)),
        (50.0, Rate(50, ntsc=False)),
        (60000 / 1001, Rate(60, ntsc=True)),
        (60.0, Rate(60, ntsc=False)),
    ],
)
def test_xml_rate_states_the_rates_of_apples_frame_rate_table(
    fps: float, rate: Rate
) -> None:
    assert xml_rate(fps) == rate


def test_a_rate_numbers_frames_at_its_frames_a_second() -> None:
    assert Rate(30, ntsc=True).fps == 30000 / 1001
    assert Rate(30, ntsc=True).frame(100.0) == 2997
    assert Rate(30, ntsc=False).frame(100.0) == 3000


def test_path_url_is_the_file_url_of_the_absolute_path_percent_encoded() -> None:
    path = Path("/data/work/7/My Clips/Café #1.mp4")

    assert path_url(path) == (
        "file://localhost/data/work/7/My%20Clips/Caf%C3%A9%20%231.mp4"
    )
    assert path_url(Path(SOURCE)) == path_url(Path.cwd() / SOURCE)


def test_build_xmeml_is_a_version_4_project_with_a_sequence_per_clip() -> None:
    clips = [
        make_clip("clean", id=3, title="Best one", start=31.26, end=47.9),
        make_clip("clean", id=5, title="Pizza", start=10.0, end=12.5),
    ]

    text = build_xmeml(clips, source())

    assert text.startswith(PROLOGUE + '<xmeml version="4">\n\t<project>\n')
    root = ET.fromstring(text)
    assert (root.tag, root.attrib) == ("xmeml", {"version": "4"})
    assert root.findtext("project/name") == "sample"
    found = root.findall("project/children/sequence")
    assert [sequence.get("id") for sequence in found] == ["sequence-1", "sequence-2"]
    assert [sequence.findtext("name") for sequence in found] == [
        "01 Best one",
        "02 Pizza",
    ]
    assert [sequence.findtext("duration") for sequence in found] == ["499", "75"]
    video = "media/video/format/samplecharacteristics/"
    audio = "media/audio/format/samplecharacteristics/"
    for sequence in found:
        assert sequence.findtext("rate/timebase") == "30"
        assert sequence.findtext("rate/ntsc") == "FALSE"
        assert sequence.findtext("timecode/string") == "00:00:00:00"
        assert sequence.findtext(f"{video}width") == "1280"
        assert sequence.findtext(f"{video}height") == "720"
        assert sequence.findtext(f"{audio}samplerate") == "48000"


def test_each_clipitem_plays_its_clips_frames_of_the_source() -> None:
    clips = [
        make_clip("clean", id=3, start=31.26, end=47.9),
        make_clip("clean", id=5, start=10.0, end=12.5),
    ]

    found = sequences(clips, source())

    # in and out are round(start * fps) and round(end * fps): 31.26 s is
    # frame 937.8 at 30 fps. The sequence plays them from its frame 0.
    expected = [("938", "1437", "0", "499"), ("300", "375", "0", "75")]
    for sequence, span in zip(found, expected, strict=True):
        items = clipitems(sequence)
        assert len(items) == 3
        for item in items:
            assert frames(item) == span
            assert item.findtext("duration") == "1800"
            assert item.findtext("name") == "sample"
            assert item.findtext("enabled") == "TRUE"


def test_clipitems_number_ntsc_frames_at_29_97_fps() -> None:
    clip = make_clip("clean", start=100.0, end=112.5)

    (sequence,) = sequences([clip], source(fps=30000 / 1001, duration=120.0))

    assert sequence.findtext("rate/timebase") == "30"
    assert sequence.findtext("rate/ntsc") == "TRUE"
    # 100 s and 112.5 s are frames 2997.003 and 3371.628 at 29.97 fps.
    for item in clipitems(sequence):
        assert frames(item) == ("2997", "3372", "0", "375")
        assert item.findtext("duration") == "3596"
        assert item.findtext("rate/ntsc") == "TRUE"


def test_the_first_clipitem_describes_the_source_file_the_rest_refer_to_it() -> None:
    clips = [make_clip("clean", id=1), make_clip("clean", id=2)]

    root = ET.fromstring(build_xmeml(clips, source()))

    files = list(root.iter("file"))
    assert len(files) == 6
    assert {file.get("id") for file in files} == {FILE_ID}
    described, *references = files
    assert next(root.iter("clipitem")).find("file") is described
    assert all(len(reference) == 0 for reference in references)
    assert described.findtext("name") == "sample"
    assert described.findtext("pathurl") == "file://localhost/data/work/7/source.mp4"
    assert described.findtext("duration") == "1800"
    assert described.findtext("rate/timebase") == "30"
    assert described.findtext("timecode/frame") == "0"
    assert described.findtext("media/video/samplecharacteristics/width") == "1280"
    assert described.findtext("media/video/samplecharacteristics/height") == "720"
    audio = "media/audio/samplecharacteristics/"
    assert described.findtext(f"{audio}samplerate") == "48000"
    assert described.findtext(f"{audio}depth") == "16"
    assert described.findtext("media/audio/channelcount") == "2"


@pytest.mark.parametrize(("channels", "tracks"), [(1, 1), (2, 2), (6, 2)])
def test_a_sequence_links_its_video_to_a_mono_channel_or_a_stereo_pair(
    channels: int, tracks: int
) -> None:
    clips = [make_clip("clean", id=1), make_clip("clean", id=2)]

    found = sequences(clips, source(channels))

    for number, sequence in enumerate(found):
        items = clipitems(sequence)
        ids = [item.get("id") for item in items]
        first = number * (1 + tracks) + 1
        assert ids == [f"clipitem-{first + index}" for index in range(1 + tracks)]
        assert len(sequence.findall("media/video/track")) == 1
        audio_tracks = sequence.findall("media/audio/track")
        assert len(audio_tracks) == tracks
        sources = [item.findtext("sourcetrack/trackindex") for item in items]
        assert sources == [None, *(str(track) for track in range(1, tracks + 1))]
        assert {item.findtext("sourcetrack/mediatype") for item in items[1:]} == {
            "audio"
        }
        outputs = [track.findtext("outputchannelindex") for track in audio_tracks]
        assert outputs == ([None] if tracks == 1 else ["1", "2"])
        links = [(ids[0], "video", "1", "1", None)] + [
            (ids[track], "audio", str(track), "1", "1")
            for track in range(1, tracks + 1)
        ]
        for item in items:
            found_links = [
                tuple(link.findtext(tag) for tag in LINK_TAGS)
                for link in item.findall("link")
            ]
            assert found_links == links


def test_names_are_escaped_and_keep_only_characters_that_xml_allows() -> None:
    meta = source().meta.model_copy(update={"title": "Tom & Jerry\x00"})
    clip = make_clip("clean", title='He said "<3"  &\x08 left 😂\n')

    root = ET.fromstring(build_xmeml([clip], Source(Path("a"), meta, 48000, 1)))

    assert root.findtext("project/name") == "Tom & Jerry"
    assert root.findtext(".//sequence/name") == '01 He said "<3" & left 😂'
    assert root.findtext(".//clipitem/name") == "Tom & Jerry"
    assert root.findtext(".//file/name") == "Tom & Jerry"


def test_sequence_numbers_have_as_many_digits_as_the_last_one() -> None:
    clips = [make_clip("clean", id=n, title="Pizza") for n in range(1, 101)]

    names = [sequence.findtext("name") for sequence in sequences(clips, source())]

    assert (names[0], names[-1]) == ("001 Pizza", "100 Pizza")


def test_a_project_without_clips_has_no_sequence_and_no_file() -> None:
    root = ET.fromstring(build_xmeml([], source()))

    children = root.find("project/children")
    assert children is not None and len(children) == 0
    assert root.find(".//file") is None


def write_work(work: Path, video: Path) -> Path:
    """Write builders.source_meta's meta.json into work and link video there
    as its source.mp4; return work."""
    work.mkdir(parents=True)
    write_json(work / META, source_meta())
    (work / SOURCE).symlink_to(video)
    return work


def test_export_premiere_writes_every_clip_best_first(
    engine: Engine, data_dir: Path, tmp_path: Path, sample_mp4: Path
) -> None:
    work = write_work(tmp_path / "work 7", sample_mp4)
    project_id = add_project(engine)
    add_clip(engine, project_id, "rendered", 70, "Good", start=20.0, end=31.5)
    add_clip(engine, project_id, "failed", 90, "Best", start=40.0, end=55.0)
    add_clip(engine, project_id, "candidate", 70, "Tie")

    path = export_premiere(engine, project_id, work)

    assert path == data_dir / "output" / str(project_id) / PREMIERE_NAME
    root = ET.parse(path).getroot()
    assert root.get("version") == "4"
    found = root.findall("project/children/sequence")
    names = [sequence.findtext("name") for sequence in found]
    assert names == ["01 Best", "02 Good", "03 Tie"]
    # sample.mp4 has 30 fps video and mono 48 kHz audio: one audio track.
    assert [[frames(item) for item in clipitems(sequence)] for sequence in found] == [
        [("1200", "1650", "0", "450")] * 2,
        [("600", "945", "0", "345")] * 2,
        [("300", "375", "0", "75")] * 2,
    ]
    assert root.findtext(".//file/pathurl") == path_url(work / SOURCE)
    assert path_url(work / SOURCE).endswith("/work%207/source.mp4")
    audio = ".//file/media/audio/"
    assert root.findtext(f"{audio}channelcount") == "1"
    assert root.findtext(f"{audio}samplecharacteristics/samplerate") == "48000"


def test_export_premiere_needs_the_project_and_an_ingested_source_with_audio(
    engine: Engine, data_dir: Path, tmp_path: Path
) -> None:
    with pytest.raises(StepError, match="project 42 not found"):
        export_premiere(engine, 42, tmp_path)

    project_id = add_project(engine)
    add_clip(engine, project_id, "candidate", 70)
    with pytest.raises(StepError, match="meta.json not found; run the ingest"):
        export_premiere(engine, project_id, tmp_path)

    write_json(tmp_path / META, source_meta())
    with pytest.raises(StepError, match="source.mp4 not found; run the ingest"):
        export_premiere(engine, project_id, tmp_path)

    silent = "testsrc=size=64x48:rate=30:duration=0.2"
    run_ffmpeg(["-f", "lavfi", "-i", silent, "-pix_fmt", "yuv420p", tmp_path / SOURCE])
    with pytest.raises(StepError, match="source.mp4 has no audio stream"):
        export_premiere(engine, project_id, tmp_path)
    assert not (data_dir / "output").exists()
