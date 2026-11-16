"""The Pro Edit critic's media (SPEC-v3 3.7, TASK-222): the sampled frames
are exactly those frames of the render, 360 px wide, and the audio summary
measures speech, music and SFX levels, the loudness curve and clipping of a
generated mix."""

import io
import wave
from pathlib import Path

import numpy as np
import pytest
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import EdlItem
from clipforge.pipeline.loudness import FLOOR_DB
from clipforge.pipeline.step import StepError
from clipforge.proedit.critic.audio_summary import summarize_audio
from clipforge.proedit.critic.sample import (
    FRAME_WIDTH,
    FrameSample,
    extract_frames,
)
from clipforge.proedit.signal_models import WordSignal
from PIL import Image as PILImage

FPS = 30
FRAMES = 37
RATE = 48_000
LUMA_STEP = 6


@pytest.fixture(scope="module")
def counting_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 37-frame 90x160 30 fps video (lossless) whose frame n is gray at
    luma 16 + 6 n (limited range, so 0..36 stay within 16..235)."""
    path = tmp_path_factory.mktemp("critic") / "counting.mp4"
    source = f"color=black:size=90x160:rate={FPS}:duration=2"
    run_ffmpeg(
        ["-f", "lavfi", "-i", source]
        + ["-vf", f"geq=lum='16+N*{LUMA_STEP}':cb=128:cr=128"]
        + ["-frames:v", str(FRAMES)]
        + ["-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p", path]
    )
    return path


def jpeg_gray(frame: int) -> float:
    """The gray of frame in a full-range JPEG: (Y - 16) x 255 / 219."""
    return frame * LUMA_STEP * 255 / 219


def mean_gray(jpeg: bytes) -> float:
    with PILImage.open(io.BytesIO(jpeg)) as picture:
        return float(np.asarray(picture.convert("L"), dtype=np.float64).mean())


def test_the_sampled_frames_are_exactly_those_frames(counting_video: Path) -> None:
    numbers = [0, 1, 7, 15, 16, 30, 36]
    samples = [FrameSample(n, n / FPS, ("test",)) for n in numbers]

    sampled = extract_frames(counting_video, samples)

    assert [s.sample for s in sampled] == samples
    for frame in sampled:
        assert (frame.width, frame.height) == (FRAME_WIDTH, 640)
        assert frame.image.media_type == "image/jpeg"
        gray = mean_gray(frame.image.data)
        assert gray == pytest.approx(jpeg_gray(frame.sample.frame), abs=1.0)


def test_a_frame_past_the_end_is_an_error(counting_video: Path) -> None:
    samples = [FrameSample(10, 10 / FPS, ()), FrameSample(40, 40 / FPS, ())]

    with pytest.raises(StepError, match="has 1 of the 2 frames"):
        extract_frames(counting_video, samples)


def write_mix(path: Path, samples: np.ndarray) -> Path:
    data = (np.clip(samples, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(data.tobytes())
    return path


def tone(amplitude: float, seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * RATE)) / RATE
    return amplitude * np.sin(2 * np.pi * 1000 * t)


def test_the_audio_summary_of_a_generated_mix(tmp_path: Path) -> None:
    # Speech (0.5) for 2 s, the bed alone (0.05) for 2 s, an SFX (0.2) for
    # 1 s, then silence with 48 full-scale samples at 5.75 s.
    tail = np.zeros(RATE)
    tail[int(0.75 * RATE) : int(0.75 * RATE) + 48] = 1.0
    mix = np.concatenate([tone(0.5, 2), tone(0.05, 2), tone(0.2, 1), tail])
    video = write_mix(tmp_path / "mix.wav", mix)
    words = [
        WordSignal(text="hello", start=0.0, end=1.0, speaker="S0", emphasis=False),
        WordSignal(text="there", start=1.0, end=2.0, speaker="S0", emphasis=True),
    ]
    items = [
        EdlItem(id=1, kind="music_bed", t_start=2.0, t_end=4.0, reason="bed"),
        EdlItem(id=2, kind="sfx", t_start=4.0, t_end=5.0, reason="hit"),
    ]

    summary = summarize_audio(video, items, words, 6.0)

    sine_db = 20 * np.log10(np.array([0.5, 0.05, 0.2]) / np.sqrt(2))
    assert summary.speech_db == pytest.approx(sine_db[0], abs=0.2)
    assert summary.music_db == pytest.approx(sine_db[1], abs=0.2)
    assert summary.sfx_db == pytest.approx(sine_db[2], abs=0.3)
    assert summary.speech_over_music_db == pytest.approx(20.0, abs=0.3)
    assert (summary.clipped_samples, summary.peak_dbfs) == (48, 0.0)
    assert len(summary.loudness_curve) == 12
    assert summary.curve_step_s == 0.5
    assert summary.loudness_curve[1] == pytest.approx(sine_db[0], abs=0.2)
    assert summary.loudness_curve[5] == pytest.approx(sine_db[1], abs=0.2)
    assert summary.loudness_curve[9] == pytest.approx(sine_db[2], abs=0.3)
    assert summary.loudness_curve[10] < sine_db[2] - 15
    assert summary.loudness_curve[11] > FLOOR_DB
    assert summary.integrated_lufs is not None
    assert summary.true_peak_dbtp is not None
    assert summary.true_peak_dbtp > -0.5


def test_a_mix_without_words_or_items_has_no_levels(tmp_path: Path) -> None:
    video = write_mix(tmp_path / "bed.wav", tone(0.1, 1.5))

    summary = summarize_audio(video, [], [], 1.5)

    assert (summary.speech_db, summary.music_db, summary.sfx_db) == (None,) * 3
    assert summary.speech_over_music_db is None
    assert summary.clipped_samples == 0
    assert len(summary.loudness_curve) == 3
