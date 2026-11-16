"""Speech enhancement with ffmpeg's own filters (SPEC-v2 3.5, the fallback of
the DeepFilterNet engine): noise reduction with afftdn (FFT denoiser) and, if
the RNNoise model is downloaded, arnndn (recurrent network for speech).

The strength slider is 0 (off) to 1 (strongest). It sets how many dB afftdn
takes the noise down by (6 to 30) and how far its residual floor lies under
the noise floor of the recording, and arnndn's mix of enhanced and original
sound. afftdn needs the noise floor to start from; it is measured as the
quietest stretch of the recording (astats RMS trough), where nobody speaks.

`enhance_speech` uses the DeepFilterNet engine (engines/deepfilternet) when
its program is there and these filters otherwise.
"""

import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from clipforge import config
from clipforge.config import Settings
from clipforge.engines.deepfilternet import deep_filter_audio, deep_filter_binary
from clipforge.enhance_model import rnnoise_model_path
from clipforge.ffmpeg import filter_value, run_ffmpeg

RUMBLE_HZ = 80
MIN_REDUCTION_DB = 6.0
MAX_REDUCTION_DB = 30.0
# Where the noise sits above its RMS in afftdn's noise_floor scale, found by
# trying noise of several levels: at this offset it is taken out completely.
NOISE_FLOOR_OFFSET_DB = 6.0
RESIDUAL_DB_AT_FULL = 20.0
# afftdn's ranges (ffmpeg -h filter=afftdn).
NOISE_FLOOR_RANGE = (-80.0, -20.0)
RESIDUAL_FLOOR_RANGE = (-80.0, -20.0)
TROUGH_FILTER = "astats=measure_perchannel=none:measure_overall=RMS_trough"
# ffmpeg prints "RMS through dB" (sic); accept the correct spelling too.
_TROUGH = re.compile(r"RMS t(?:rough|hrough) dB: (\S+)")


def enhance_filter(
    strength: float, noise_floor_db: float, rnn_model: Path | None = None
) -> str:
    """Return the audio filter that enhances speech at strength (0 to 1) in a
    recording whose quietest stretch is at noise_floor_db (dBFS RMS), or ""
    if strength is 0. It cuts rumble under 80 Hz, runs arnndn if rnn_model
    (an RNNoise .rnnn file) is given and ends with afftdn. Raises ValueError
    if strength is outside 0 to 1."""
    if not 0.0 <= strength <= 1.0:
        raise ValueError(f"enhancement strength {strength} is not between 0 and 1")
    if strength == 0.0:
        return ""
    reduction = MIN_REDUCTION_DB + (MAX_REDUCTION_DB - MIN_REDUCTION_DB) * strength
    floor = _clamp(noise_floor_db + NOISE_FLOOR_OFFSET_DB, NOISE_FLOOR_RANGE)
    residual = _clamp(floor - RESIDUAL_DB_AT_FULL * strength, RESIDUAL_FLOOR_RANGE)
    denoise = f"afftdn=nr={reduction:.1f}:nf={floor:.1f}:rf={residual:.1f}"
    filters = [f"highpass=f={RUMBLE_HZ}"]
    if rnn_model is not None:
        model = filter_value(str(rnn_model))
        filters.append(f"arnndn=m={model}:mix={strength:.2f}")
    return ",".join([*filters, denoise])


def measure_noise_floor(src: Path) -> float:
    """Return the RMS level in dBFS of the quietest stretch (50 ms) of src's
    first audio stream, as astats measures it: -inf for digital silence.
    Raises FFmpegError if ffmpeg fails (e.g. src has no audio)."""
    stderr = run_ffmpeg(
        ["-i", src, "-map", "0:a:0", "-af", TROUGH_FILTER, "-f", "null", "-"],
        loglevel="info",
    ).stderr.decode(errors="replace")
    return float(_TROUGH.findall(stderr)[-1])


def enhance_audio(
    src: Path, dst: Path, strength: float, cfg: Settings | None = None
) -> Path:
    """Write the sound of src (audio or video file) enhanced at strength (0
    to 1) to dst, 16-bit PCM WAV, and return dst. arnndn is used if its model
    is downloaded to cfg.models_dir (settings by default). Raises ValueError
    if strength is outside 0 to 1 and FFmpegError if ffmpeg fails."""
    cfg = cfg or config.settings
    model = rnnoise_model_path(cfg)
    audio_filter = enhance_filter(
        strength,
        measure_noise_floor(src) if strength > 0 else 0.0,
        model if model.is_file() else None,
    )
    run_ffmpeg(
        [
            "-i",
            src,
            "-map",
            "0:a:0",
            "-af",
            audio_filter or "anull",
            "-c:a",
            "pcm_s16le",
            dst,
        ]
    )
    return dst


SpeechEngine = Literal["deepfilternet", "ffmpeg"]


def enhance_speech(
    src: Path, dst: Path, strength: float, cfg: Settings | None = None
) -> SpeechEngine:
    """Write the sound of src enhanced at strength (0 to 1) to dst, a 16-bit
    PCM WAV, with DeepFilterNet if its program is found (48 kHz) and with
    ffmpeg's filters otherwise; return the engine used. Raises ValueError if
    strength is outside 0 to 1, DeepFilterError if deep-filter fails and
    FFmpegError if ffmpeg fails."""
    if deep_filter_binary(cfg) is not None:
        deep_filter_audio(src, dst, strength, cfg)
        return "deepfilternet"
    enhance_audio(src, dst, strength, cfg)
    return "ffmpeg"


def enhance_span(
    source: Path,
    start: float,
    end: float,
    dst: Path,
    strength: float,
    cfg: Settings | None = None,
) -> SpeechEngine:
    """Write the sound of source from start to end seconds, enhanced at
    strength (0 to 1), to dst, a 16-bit PCM WAV that begins at start (as an
    ffmpeg input read from start does), and return the engine used
    (enhance_speech). Raises what enhance_speech raises."""
    with tempfile.TemporaryDirectory(prefix="clipforge-span-", dir=dst.parent) as work:
        span = Path(work) / "span.wav"
        run_ffmpeg(
            [
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{end - start:.3f}",
                "-i",
                source,
                "-map",
                "0:a:0",
                "-c:a",
                "pcm_s16le",
                span,
            ]
        )
        return enhance_speech(span, dst, strength, cfg)


@contextmanager
def enhanced_voice(
    source: Path,
    start: float,
    end: float,
    strength: float,
    cfg: Settings | None = None,
) -> Iterator[Path | None]:
    """Yield the WAV of source's sound from start to end seconds enhanced at
    strength (enhance_span), which is deleted afterwards; None, with no
    work, if strength is 0. Raises what enhance_span raises."""
    if strength <= 0.0:
        yield None
        return
    with tempfile.TemporaryDirectory(prefix="clipforge-voice-") as work:
        voice = Path(work) / "voice.wav"
        enhance_span(source, start, end, voice, strength, cfg)
        yield voice


def _clamp(value: float, limits: tuple[float, float]) -> float:
    """Return value limited to the range limits (low, high)."""
    return max(limits[0], min(limits[1], value))
