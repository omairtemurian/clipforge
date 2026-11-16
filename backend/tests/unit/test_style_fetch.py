"""Tests of fetching style references (SPEC-v3 1.4, 4.1, 4.2).

They run the real yt-dlp (format selection, the generic extractor, the
download, the ffmpeg merge) and the real ffprobe; only the network is
replaced: extract_info answers from canned pages whose formats are file://
URLs of small generated files, and a link to a media file is read from a
local file. The checks are about what stays on disk: the media directory is
gone after a success, a failed download, a refused video and an analyzer
exception.
"""

import shutil
from pathlib import Path
from typing import Any

import pytest
from clipforge.pipeline.step import StepError
from clipforge.proedit.style import fetch
from clipforge.proedit.style.fetch import (
    MAX_HEIGHT,
    STYLE_FORMAT,
    ReferenceBusy,
    StyleFetchError,
    analyze_reference,
    style_dir,
    validate_links,
)
from style_fakes import (
    BROKEN_PAGE,
    DIRECT,
    LONG_PAGE,
    PAGE,
    Web,
    fmt,
    make_video,
    offline_web,  # noqa: F401
    page,
    small_reference,  # noqa: F401
)


def measured(path: Path) -> dict[str, Any]:
    """An analyzer: checks the file is there and returns numbers."""
    assert path.is_file()
    return {"size": path.stat().st_size}


def test_links_are_stripped_deduplicated_and_kept_in_order() -> None:
    links = validate_links([f" {PAGE} ", LONG_PAGE, PAGE])

    assert links == [PAGE, LONG_PAGE]


@pytest.mark.parametrize(
    ("urls", "message"),
    [
        ([], "at least one link"),
        (["  "], "at least one link"),
        ([f"https://www.youtube.com/watch?v=ref{n}" for n in range(6)], "at most 5"),
        (["ftp://example.com/a.mp4"], "is not an http"),
        (["/Users/me/video.mp4"], "is not an http"),
        (["https://example.com/some/page"], "example.com"),
    ],
)
def test_no_links_too_many_or_unsupported_links_are_refused(
    urls: list[str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_links(urls)


def test_five_links_are_accepted() -> None:
    urls = [f"https://www.youtube.com/watch?v=ref{n}" for n in range(5)]

    assert validate_links(urls) == urls


def test_media_is_analyzed_at_720p_at_most_and_deleted_afterwards(
    web: Web, small: Path, tmp_path: Path
) -> None:
    missing = tmp_path / "missing-1080.mp4"
    web.pages[PAGE] = page(60, fmt("18", small, 240), fmt("37", missing, 1080))
    seen: list[Path] = []
    directory = style_dir(7)
    directory.mkdir(parents=True)
    (directory / "old.mp4").write_bytes(b"left over from a crash")

    def analyzer(path: Path) -> dict[str, Any]:
        seen.append(path)
        assert path.parent == directory
        assert [p.name for p in directory.iterdir()] == [path.name]
        return measured(path)

    result = analyze_reference(PAGE, 7, analyzer)

    assert result["size"] > 0
    assert seen[0].parent == directory
    assert not directory.exists()
    assert [p["format"] for p in web.params if "format" in p] == [STYLE_FORMAT]
    assert STYLE_FORMAT == "bv*[height<=720]+ba/b[height<=720]"


def test_the_media_is_deleted_when_the_analyzer_raises(web: Web, small: Path) -> None:
    web.pages[PAGE] = page(60, fmt("18", small, 240))
    paths: list[Path] = []

    def analyzer(path: Path) -> dict[str, Any]:
        paths.append(path)
        raise RuntimeError("analysis blew up")

    with pytest.raises(RuntimeError, match="analysis blew up"):
        analyze_reference(PAGE, 8, analyzer)

    assert paths[0].name.startswith("download.")
    assert not paths[0].exists()
    assert not style_dir(8).exists()


def test_the_directory_is_gone_when_the_page_cannot_be_read(web: Web) -> None:
    with pytest.raises(StepError, match="Video unavailable"):
        analyze_reference(BROKEN_PAGE, 9, measured)

    assert not style_dir(9).exists()


def test_the_directory_is_gone_when_the_download_fails(
    web: Web, tmp_path: Path
) -> None:
    web.pages[PAGE] = page(60, fmt("18", tmp_path / "not-there.mp4", 240))

    with pytest.raises(StepError):
        analyze_reference(PAGE, 10, measured)

    assert not style_dir(10).exists()


def test_a_video_longer_than_3_minutes_is_refused_before_downloading(
    web: Web, small: Path
) -> None:
    web.pages[LONG_PAGE] = page(181, fmt("18", small, 240))
    calls: list[Path] = []

    def analyzer(path: Path) -> dict[str, Any]:
        calls.append(path)
        return {}

    with pytest.raises(StyleFetchError, match="3 min"):
        analyze_reference(LONG_PAGE, 11, analyzer)

    assert calls == []
    assert not style_dir(11).exists()
    assert all("format" not in p for p in web.params)


def test_3_minutes_exactly_is_accepted(web: Web, small: Path) -> None:
    web.pages[PAGE] = page(180, fmt("18", small, 240))

    assert analyze_reference(PAGE, 12, measured)["size"] > 0


def test_a_direct_link_longer_than_3_minutes_is_refused_after_the_download(
    web: Web, tmp_path: Path
) -> None:
    web.direct = make_video(tmp_path / "long.mp4", "64x64", 181.0, rate=1)

    with pytest.raises(StyleFetchError, match="3 min"):
        analyze_reference(DIRECT, 13, measured)

    assert not style_dir(13).exists()


def test_a_direct_link_taller_than_720p_is_refused_after_the_download(
    web: Web, tmp_path: Path
) -> None:
    web.direct = make_video(tmp_path / "tall.mp4", "1920x1080", 1.0, rate=5)

    with pytest.raises(StyleFetchError, match=f"1080p.*{MAX_HEIGHT}p"):
        analyze_reference(DIRECT, 14, measured)

    assert not style_dir(14).exists()


def test_a_direct_link_within_the_limits_is_analyzed(web: Web, small: Path) -> None:
    web.direct = small

    assert analyze_reference(DIRECT, 15, measured)["size"] > 0
    assert not style_dir(15).exists()


def test_a_reference_is_not_fetched_twice_at_once(web: Web, small: Path) -> None:
    web.pages[PAGE] = page(60, fmt("18", small, 240))

    def analyzer(path: Path) -> dict[str, Any]:
        with pytest.raises(ReferenceBusy, match="being analyzed"):
            analyze_reference(PAGE, 16, measured)
        assert path.is_file()
        return {}

    analyze_reference(PAGE, 16, analyzer)

    assert not style_dir(16).exists()
    assert analyze_reference(PAGE, 16, measured)["size"] > 0


def test_media_that_cannot_be_deleted_is_an_error(
    web: Web, small: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web.pages[PAGE] = page(60, fmt("18", small, 240))
    with monkeypatch.context() as patch:
        patch.setattr(fetch.shutil, "rmtree", lambda *a, **k: None)
        with pytest.raises(StyleFetchError, match="could not delete"):
            analyze_reference(PAGE, 17, measured)

    shutil.rmtree(style_dir(17))
