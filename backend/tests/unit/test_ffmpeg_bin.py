"""Tests of how the ffmpeg and ffprobe binaries are resolved and checked."""

import stat
from pathlib import Path

import pytest
from clipforge import config
from clipforge.config import Settings
from clipforge.ffmpeg import (
    LIBASS_MISSING,
    FFmpegError,
    check_ffmpeg,
    ffmpeg_bin,
    ffprobe_bin,
)


@pytest.fixture
def full_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A stand-in for ffmpeg-full's bin directory, with no binaries in it."""
    directory = tmp_path / "ffmpeg-full" / "bin"
    directory.mkdir(parents=True)
    monkeypatch.setattr(config, "FFMPEG_FULL_BIN_DIR", directory)
    monkeypatch.chdir(tmp_path)
    for name in ("FFMPEG_BIN", "FFPROBE_BIN"):
        monkeypatch.delenv(name, raising=False)
    return directory


def _fake_ffmpeg(path: Path, filters: str) -> str:
    """Write a script that prints filters for `-filters`; return its path."""
    path.write_text(f"#!/bin/sh\ncat <<'EOF'\n{filters}\nEOF\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def test_without_ffmpeg_full_the_tools_come_from_path(full_dir: Path) -> None:
    settings = Settings()

    assert (settings.ffmpeg_bin, settings.ffprobe_bin) == ("ffmpeg", "ffprobe")


def test_ffmpeg_full_wins_over_path_when_installed(full_dir: Path) -> None:
    (full_dir / "ffmpeg").touch()
    (full_dir / "ffprobe").touch()
    settings = Settings()

    assert settings.ffmpeg_bin == str(full_dir / "ffmpeg")
    assert settings.ffprobe_bin == str(full_dir / "ffprobe")


def test_environment_and_yaml_override_ffmpeg_full(
    full_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (full_dir / "ffmpeg").touch()
    (full_dir / "ffprobe").touch()
    (tmp_path / "config.yaml").write_text("ffprobe_bin: /yaml/ffprobe\n")
    assert Settings().ffprobe_bin == "/yaml/ffprobe"

    monkeypatch.setenv("FFMPEG_BIN", "/env/ffmpeg")
    monkeypatch.setenv("FFPROBE_BIN", "/env/ffprobe")
    settings = Settings()

    assert (settings.ffmpeg_bin, settings.ffprobe_bin) == (
        "/env/ffmpeg",
        "/env/ffprobe",
    )


def test_empty_values_fall_back_to_the_default(
    full_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FFMPEG_BIN", "")
    monkeypatch.setenv("FFPROBE_BIN", " ")

    assert (Settings().ffmpeg_bin, Settings().ffprobe_bin) == ("ffmpeg", "ffprobe")


def test_helpers_read_the_current_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "ffmpeg_bin", "/x/ffmpeg")
    monkeypatch.setattr(config.settings, "ffprobe_bin", "/x/ffprobe")

    assert (ffmpeg_bin(), ffprobe_bin()) == ("/x/ffmpeg", "/x/ffprobe")


def test_check_ffmpeg_passes_with_the_subtitles_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    filters = " T.. scale  V->V  Scale.\n ... subtitles  V->V  Render text."
    fake = _fake_ffmpeg(tmp_path / "ffmpeg", filters)
    monkeypatch.setattr(config.settings, "ffmpeg_bin", fake)

    check_ffmpeg()


def test_check_ffmpeg_without_libass_explains_the_fix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _fake_ffmpeg(tmp_path / "ffmpeg", " T.. scale  V->V  Scale.")
    monkeypatch.setattr(config.settings, "ffmpeg_bin", fake)

    with pytest.raises(FFmpegError) as info:
        check_ffmpeg()

    assert str(info.value) == LIBASS_MISSING
    assert str(info.value) == (
        "ffmpeg lacks libass (subtitles filter); install with: brew install ffmpeg-full"
    )


def test_check_ffmpeg_with_a_missing_binary_raises_ffmpeg_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config.settings, "ffmpeg_bin", str(tmp_path / "nope"))

    with pytest.raises(FFmpegError, match="not found"):
        check_ffmpeg()
