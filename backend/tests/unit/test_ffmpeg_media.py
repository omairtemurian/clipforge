"""Tests for what clipforge.ffmpeg's helpers report and write for real media.

Media other than the committed sample is generated with ffmpeg's lavfi
sources or derived from the sample, then read back with ffmpeg and ffprobe.
"""

import math
import sys
import wave
from array import array
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from clipforge.ffmpeg import (
    WAV_SAMPLE_RATE,
    FFmpegError,
    extract_audio_wav,
    extract_frame,
    ffprobe_json,
    probe_media,
    run_ffmpeg,
)

FRAME_TIME = 6.0
# Sample magnitude above which the fixture's digitally silent audio has sound.
SILENCE = 100


def rgb(path: Path, video_filter: str | None = None) -> bytes:
    """Decode the first frame of path (after an optional filter) to RGB bytes."""
    vf = [] if video_filter is None else ["-vf", video_filter]
    args: list[str | Path] = ["-i", path, *vf, "-frames:v", "1"]
    return run_ffmpeg([*args, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]).stdout


def read_wav(path: Path) -> tuple[tuple[int, int, int], Sequence[int]]:
    """Return (channels, sample width, sample rate) and the samples of a WAV."""
    with wave.open(str(path), "rb") as wav:
        params = (wav.getnchannels(), wav.getsampwidth(), wav.getframerate())
        samples = array("h", wav.readframes(wav.getnframes()))
    if sys.byteorder == "big":
        samples.byteswap()
    return params, samples


def level_db(samples: Sequence[int], start: float, end: float) -> float:
    """RMS level in dBFS of the samples between start and end seconds."""
    window = samples[int(start * WAV_SAMPLE_RATE) : int(end * WAV_SAMPLE_RATE)]
    rms = math.sqrt(sum(sample * sample for sample in window) / len(window))
    return 20 * math.log10(max(rms, 1.0) / 32768)


@pytest.fixture(scope="module")
def other_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 1 s Matroska clip: 320x240 mpeg4 at 29.97 fps, 44.1 kHz stereo PCM."""
    path = tmp_path_factory.mktemp("other") / "other.mkv"
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30000/1001:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100:duration=1",
            "-ac", "2", "-c:v", "mpeg4", "-c:a", "pcm_s16le", path,
        ]
    )  # fmt: skip
    return path


def test_probe_media_returns_the_fixture_values(
    sample_mp4: Path, expected: dict[str, Any]
) -> None:
    assert asdict(probe_media(sample_mp4)) == expected["media"]


def test_ffprobe_json_reports_the_format_and_streams(
    sample_mp4: Path, expected: dict[str, Any]
) -> None:
    media = expected["media"]
    report = ffprobe_json(sample_mp4)
    assert report["format"]["tags"]["title"] == media["title"]
    codecs = {
        stream["codec_type"]: stream["codec_name"] for stream in report["streams"]
    }
    assert codecs == {"video": media["video_codec"], "audio": media["audio_codec"]}


def test_probe_media_reads_other_containers_and_codecs(other_clip: Path) -> None:
    media = asdict(probe_media(other_clip))
    assert media.pop("duration") == pytest.approx(1.0, abs=0.05)
    assert media == {
        "width": 320,
        "height": 240,
        "fps": 30000 / 1001,
        "video_codec": "mpeg4",
        "pix_fmt": "yuv420p",
        "audio_codec": "pcm_s16le",
        "sample_rate": 44100,
        "channels": 2,
        "title": None,
    }


def test_probe_media_reports_the_average_rate_of_variable_rate_video(
    tmp_path: Path,
) -> None:
    vfr = tmp_path / "vfr.mp4"
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30:duration=1",
            "-vf", "select=not(eq(mod(n\\,3)\\,0))", "-fps_mode", "passthrough",
            "-c:v", "mpeg4", vfr,
        ]
    )  # fmt: skip
    (stream,) = ffprobe_json(vfr)["streams"]
    assert stream["r_frame_rate"] == "30/1"
    info = probe_media(vfr)
    assert info.fps == pytest.approx(int(stream["nb_frames"]) / info.duration)
    assert info.fps < 25


def test_video_without_audio_has_no_audio_fields_or_wav(
    other_clip: Path, tmp_path: Path
) -> None:
    silent = tmp_path / "silent.mkv"
    run_ffmpeg(["-i", other_clip, "-map", "0:v", "-c", "copy", silent])
    info = probe_media(silent)
    assert info.width == 320
    assert (info.audio_codec, info.sample_rate, info.channels) == (None, None, None)
    with pytest.raises(FFmpegError, match="matches no streams"):
        extract_audio_wav(silent, tmp_path / "silent.wav")


@pytest.mark.parametrize(
    ("degrees", "swapped"), [(90, True), (180, False), (270, True)]
)
def test_rotated_video_reports_its_displayed_size(
    degrees: int,
    swapped: bool,
    sample_mp4: Path,
    expected: dict[str, Any],
    tmp_path: Path,
) -> None:
    coded = (expected["media"]["width"], expected["media"]["height"])
    displayed = coded[::-1] if swapped else coded
    rotated = tmp_path / "rotated.mp4"
    run_ffmpeg(
        [
            "-display_rotation", str(degrees), "-i", sample_mp4,
            "-t", "1", "-c", "copy", rotated,
        ]
    )  # fmt: skip
    streams = ffprobe_json(rotated)["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    assert (video["width"], video["height"]) == coded

    info = probe_media(rotated)
    assert (info.width, info.height) == displayed
    (frame,) = ffprobe_json(extract_frame(rotated, tmp_path / "f.png", 0.0))["streams"]
    assert (frame["width"], frame["height"]) == displayed


def test_probe_media_rejects_audio_files_and_still_images(
    sample_mp4: Path, tmp_path: Path
) -> None:
    tone = tmp_path / "tone.wav"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=sample_rate=16000:duration=1", tone])
    still = extract_frame(sample_mp4, tmp_path / "still.png", 0.0)
    cover_art = tmp_path / "cover.m4a"
    run_ffmpeg(
        [
            "-i", tone, "-i", still, "-map", "0:a:0", "-map", "1:v:0",
            "-c:a", "aac", "-c:v", "copy",
            "-disposition:v:0", "attached_pic", cover_art,
        ]
    )  # fmt: skip
    streams = ffprobe_json(cover_art)["streams"]
    assert [stream["codec_type"] for stream in streams] == ["audio", "video"]

    for audio_only in (tone, cover_art):
        with pytest.raises(FFmpegError, match="^no video stream in "):
            probe_media(audio_only)
    with pytest.raises(FFmpegError, match="^unknown duration for "):
        probe_media(still)


def test_extract_frame_saves_the_first_frame_at_the_time(
    sample_mp4: Path, expected: dict[str, Any], tmp_path: Path
) -> None:
    media = expected["media"]
    index = round(FRAME_TIME * media["fps"])
    png = tmp_path / "frame.png"
    extract_frame(sample_mp4, png, 0.0)
    assert extract_frame(sample_mp4, png, FRAME_TIME) == png

    pixels = rgb(png)
    assert len(pixels) == media["width"] * media["height"] * 3
    assert pixels == rgb(sample_mp4, f"select=eq(n\\,{index})")
    for neighbour in (index - 1, index + 1):
        assert pixels != rgb(sample_mp4, f"select=eq(n\\,{neighbour})")


def test_extract_frame_writes_a_full_size_jpeg(
    sample_mp4: Path, expected: dict[str, Any], tmp_path: Path
) -> None:
    jpeg = extract_frame(sample_mp4, tmp_path / "thumb.jpg", FRAME_TIME)
    assert jpeg.read_bytes().startswith(b"\xff\xd8\xff")
    (stream,) = ffprobe_json(jpeg)["streams"]
    size = (expected["media"]["width"], expected["media"]["height"])
    assert (stream["codec_name"], stream["width"], stream["height"]) == ("mjpeg", *size)


def test_extract_frame_past_the_end_fails_without_writing(
    sample_mp4: Path, expected: dict[str, Any], tmp_path: Path
) -> None:
    late = tmp_path / "late.jpg"
    with pytest.raises(FFmpegError, match="Nothing was written into output file"):
        extract_frame(sample_mp4, late, expected["media"]["duration"])
    assert not late.exists()


def test_extract_frame_rejects_a_negative_time(
    sample_mp4: Path, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="must be >= 0"):
        extract_frame(sample_mp4, tmp_path / "early.jpg", -0.5)


def test_extract_audio_wav_writes_time_aligned_16k_mono_pcm(
    sample_mp4: Path, expected: dict[str, Any], tmp_path: Path
) -> None:
    params, samples = read_wav(extract_audio_wav(sample_mp4, tmp_path / "audio.wav"))
    assert params == (1, 2, WAV_SAMPLE_RATE)
    duration = expected["media"]["duration"]
    assert len(samples) == pytest.approx(duration * WAV_SAMPLE_RATE, abs=1600)

    first_sound = next(i for i, sample in enumerate(samples) if abs(sample) > SILENCE)
    speech_start = expected["speech"][0]["start"]
    assert first_sound / WAV_SAMPLE_RATE == pytest.approx(speech_start, abs=0.02)
    for laugh in expected["laughs"]:
        assert level_db(samples, laugh["start"] + 0.1, laugh["end"] - 0.1) > -25


def test_extract_audio_wav_downmixes_and_resamples(
    other_clip: Path, tmp_path: Path
) -> None:
    params, samples = read_wav(extract_audio_wav(other_clip, tmp_path / "audio.wav"))
    assert params == (1, 2, WAV_SAMPLE_RATE)
    assert len(samples) == pytest.approx(WAV_SAMPLE_RATE, abs=160)
    assert level_db(samples, 0.1, 0.9) > -30


def test_extract_audio_wav_cuts_a_window_of_a_wav_to_the_sample(
    sample_mp4: Path, tmp_path: Path
) -> None:
    full = extract_audio_wav(sample_mp4, tmp_path / "audio.wav")
    _, samples = read_wav(full)

    window = extract_audio_wav(full, tmp_path / "w.wav", start=2.5, duration=1.25)
    params, cut = read_wav(window)
    assert params == (1, 2, WAV_SAMPLE_RATE)
    first = int(2.5 * WAV_SAMPLE_RATE)
    assert cut == samples[first : first + int(1.25 * WAV_SAMPLE_RATE)]

    _, tail = read_wav(extract_audio_wav(full, tmp_path / "t.wav", start=58.0))
    assert tail == samples[58 * WAV_SAMPLE_RATE :]
    _, rest = read_wav(extract_audio_wav(full, tmp_path / "r.wav", duration=90.0))
    assert rest == samples


@pytest.mark.parametrize(
    ("start", "duration", "message"),
    [(-1.0, None, "start must be >= 0"), (0.0, 0.0, "duration must be > 0")],
)
def test_extract_audio_wav_rejects_a_bad_window(
    sample_mp4: Path, tmp_path: Path, start: float, duration: float | None, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        extract_audio_wav(
            sample_mp4, tmp_path / "a.wav", start=start, duration=duration
        )
