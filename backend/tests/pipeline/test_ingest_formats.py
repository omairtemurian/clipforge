"""Tests of the yt-dlp format preference of URL sources: H.264/AAC first, so
that a YouTube video needs no conversion, other codecs only when a page has
no H.264; the 1080p limit holds either way.

Selection runs the installed yt-dlp on canned format lists (simulate, no
download); the ingest tests download local files through test_ingest_url's
offline YoutubeDL.
"""

from pathlib import Path
from typing import Any

import pytest
import yt_dlp
from clipforge.ffmpeg import probe_media
from clipforge.pipeline.download import FORMAT_SORT, YTDLP_FORMAT, ytdlp_options
from clipforge.pipeline.ingest import CONVERT_START, SOURCE, SOURCE_READY
from test_ingest_url import URL, Web, fmt, ingest_url, page, web  # noqa: F401

MakeMedia = Any

H264_1080 = ("h264-1080", "avc1.640028", 1080)
H264_720 = ("h264-720", "avc1.4d401f", 720)
AV1_1080 = ("av1-1080", "av01.0.08M.08", 1080)
VP9_1080 = ("vp9-1080", "vp9", 1080)
AV1_2160 = ("av1-2160", "av01.0.12M.08", 2160)


def video(format_id: str, codec: str, height: int) -> dict[str, Any]:
    """A video-only format entry."""
    return {
        "format_id": format_id,
        "url": f"https://media.example/{format_id}",
        "ext": "webm" if codec == "vp9" else "mp4",
        "vcodec": codec,
        "acodec": "none",
        "height": height,
        "width": height * 16 // 9,
        "tbr": height * 3.0,
        "protocol": "https",
    }


def audio(format_id: str, codec: str, ext: str) -> dict[str, Any]:
    """An audio-only format entry; Opus has the higher bitrate, as on YouTube."""
    return {
        "format_id": format_id,
        "url": f"https://media.example/{format_id}",
        "ext": ext,
        "vcodec": "none",
        "acodec": codec,
        "tbr": 130.0 if codec == "opus" else 128.0,
        "protocol": "https",
    }


AUDIO = [audio("251", "opus", "webm"), audio("140", "mp4a.40.2", "m4a")]


def chosen(
    tmp_path: Path, videos: list[tuple[str, str, int]], format_sort: list[str]
) -> list[str]:
    """The format ids yt-dlp picks from videos + AUDIO with the download
    options of ingest (and format_sort)."""
    params: Any = {
        **ytdlp_options(tmp_path, lambda event: None),
        "format_sort": format_sort,
        "simulate": True,
    }
    info = {
        "id": "clipforge01",
        "title": "Live VOD",
        "extractor": "youtube",
        "extractor_key": "Youtube",
        "webpage_url": URL,
        "formats": [video(*spec) for spec in videos] + [dict(a) for a in AUDIO],
    }
    with yt_dlp.YoutubeDL(params) as ydl:
        result = ydl.process_ie_result(info, download=False)
    return [f["format_id"] for f in result["requested_formats"]]


def test_download_options_prefer_h264_and_aac(tmp_path: Path) -> None:
    options: Any = ytdlp_options(tmp_path, lambda event: None)
    assert options["format_sort"] == FORMAT_SORT == ["vcodec:h264", "res", "acodec:m4a"]
    assert options["format"] == YTDLP_FORMAT


def test_without_a_sort_yt_dlp_would_pick_av1_and_opus(tmp_path: Path) -> None:
    """The owner's 2 h live VOD case: the default sort picks AV1 + Opus."""
    assert chosen(tmp_path, [AV1_1080, H264_1080], []) == ["av1-1080", "251"]


@pytest.mark.parametrize(
    ("videos", "expected"),
    [
        ([AV1_1080, VP9_1080, H264_1080, H264_720, AV1_2160], ["h264-1080", "140"]),
        ([AV1_1080, H264_720], ["h264-720", "140"]),
        ([AV1_1080, VP9_1080, AV1_2160], ["vp9-1080", "140"]),
        ([AV1_1080, AV1_2160], ["av1-1080", "140"]),
    ],
)
def test_h264_aac_is_preferred_and_other_codecs_are_the_fallback(
    tmp_path: Path, videos: list[tuple[str, str, int]], expected: list[str]
) -> None:
    assert chosen(tmp_path, videos, FORMAT_SORT) == expected


def test_h264_page_is_ingested_without_a_conversion(
    web: Web,  # noqa: F811
    make_media: MakeMedia,
    tmp_path: Path,
) -> None:
    h264 = make_media(
        "h264-480.mp4", "-c:v", "libx264", "-pix_fmt", "yuv420p", size="854x480",
        audio=False,
    )  # fmt: skip
    aac = make_media("aac.m4a", "-c:a", "aac", size=None)
    web.pages[URL] = page(
        fmt("av1", tmp_path / "missing-av1.mp4", "mp4", vcodec="av01", acodec="none",
            height=1080, tbr=3000),
        fmt("avc", h264, "mp4", vcodec="avc1", acodec="none", height=480, tbr=900),
        fmt("opus", tmp_path / "missing.webm", "webm", vcodec="none", acodec="opus",
            tbr=160),
        fmt("aac", aac, "m4a", vcodec="none", acodec="mp4a", tbr=128),
    )  # fmt: skip
    meta, progress = ingest_url(tmp_path / "job")
    assert (meta.width, meta.height) == (854, 480)
    assert not [value for value in progress if CONVERT_START <= value < SOURCE_READY]
    info = probe_media(tmp_path / "job" / SOURCE)
    assert (info.video_codec, info.audio_codec) == ("h264", "aac")


def test_vp9_only_page_is_downloaded_then_converted(
    web: Web,  # noqa: F811
    make_media: MakeMedia,
    tmp_path: Path,
) -> None:
    vp9 = make_media(
        "vp9-only.webm", "-c:v", "libvpx-vp9", "-deadline", "realtime",
        "-cpu-used", "8", audio=False,
    )  # fmt: skip
    opus = make_media("opus.webm", "-c:a", "libopus", size=None)
    web.pages[URL] = page(
        fmt("vp9", vp9, "webm", vcodec="vp9", acodec="none", height=240),
        fmt("opus", opus, "webm", vcodec="none", acodec="opus"),
    )
    _, progress = ingest_url(tmp_path / "job")
    assert CONVERT_START in progress
    info = probe_media(tmp_path / "job" / SOURCE)
    assert (info.video_codec, info.audio_codec) == ("h264", "aac")
