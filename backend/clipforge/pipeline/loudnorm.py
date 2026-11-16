"""Two-pass loudness normalization of a clip's audio (SPEC 6.11).

ffmpeg's loudnorm filter (EBU R128) brings a rendered clip to the project's
target_lufs in two passes over its audio, as it is after the clip's cuts:

1. measure_loudness runs the audio through loudnorm with print_format=json
   (measure_filter) and reads back the measurement that loudnorm reports
   once the stream ends (parse_loudness);
2. the render passes the audio through normalize_filter: loudnorm with that
   measurement in linear mode, which turns the whole clip up or down by one
   gain. loudnorm itself falls back to its dynamic mode when that gain would
   take the true peak over TRUE_PEAK_DBTP or the clip's loudness range is
   wider than LOUDNESS_RANGE_LU.

loudnorm works at 192 kHz, so its output is resampled to SAMPLE_RATE. Its
output timestamps are rebuilt from the sample count (asetpts), because
loudnorm gets them wrong in two ways: after concat (a render's cuts), whose
time base is not 1 / sample rate, they advance too little, and at the end of
any stream they jump ahead before its last block.
"""

import json
import logging
import math
from collections.abc import Sequence
from dataclasses import astuple, dataclass

from clipforge.ffmpeg import Arg, FFmpegError, ffmpeg_bin, run_ffmpeg

logger = logging.getLogger(__name__)

# loudnorm's default targets for the true peak and the loudness range.
TRUE_PEAK_DBTP = -2.0
LOUDNESS_RANGE_LU = 7.0
SAMPLE_RATE = 48_000
# loudnorm logs its report as JSON after a "[Parsed_loudnorm_N @ 0x...]" prefix.
REPORT_PREFIX = "[Parsed_loudnorm_"
# The keys of the report's measurement, in the order of Loudness's fields.
REPORT_KEYS = ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")
# The second pass's loudnorm options for those fields, with their ranges.
MEASURED_OPTIONS = (
    ("measured_i", -99.0, 0.0),
    ("measured_tp", -99.0, 99.0),
    ("measured_lra", 0.0, 99.0),
    ("measured_thresh", -99.0, 0.0),
    ("offset", -99.0, 99.0),
)


@dataclass(frozen=True, slots=True)
class Loudness:
    """loudnorm's measurement of a clip's audio: its integrated loudness
    (LUFS), true peak (dBTP), loudness range (LU) and gating threshold
    (LUFS), and the offset (LU) by which the second pass corrects its gain
    to reach the target."""

    integrated: float
    true_peak: float
    loudness_range: float
    threshold: float
    offset: float


def measure_filter(target_lufs: float) -> str:
    """Return the loudnorm filter of the first pass, which measures audio for
    a target of target_lufs and reports the measurement as JSON."""
    return f"loudnorm={_targets(target_lufs)}:print_format=json"


def normalize_filter(target_lufs: float, loudness: Loudness) -> str:
    """Return the audio filters of the second pass, which bring audio that the
    first pass measured as loudness to target_lufs (module docstring).

    Measured values are kept within the ranges of loudnorm's options.
    """
    measured = (
        f"{name}={min(max(value, low), high):.2f}"
        for value, (name, low, high) in zip(
            astuple(loudness), MEASURED_OPTIONS, strict=True
        )
    )
    return (
        f"loudnorm={_targets(target_lufs)}:{':'.join(measured)}:linear=true,"
        f"aresample={SAMPLE_RATE},asetpts=N/SR/TB+STARTPTS"
    )


def parse_loudness(stderr: str) -> Loudness | None:
    """Return the measurement in the last loudnorm report in stderr (ffmpeg's
    log at the info level), or None if its values are not finite, as they
    are for silence. Raises ValueError if stderr holds no valid report."""
    prefix = stderr.rfind(REPORT_PREFIX)
    brace = stderr.find("{", prefix) if prefix >= 0 else -1
    if brace < 0:
        raise ValueError("loudnorm reported no measurement")
    try:
        report, _ = json.JSONDecoder().raw_decode(stderr, brace)
        values = [float(report[key]) for key in REPORT_KEYS]
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"loudnorm's report is not valid: {exc!r}") from exc
    if not all(math.isfinite(value) for value in values):
        return None
    return Loudness(*values)


def measure_loudness(inputs: Sequence[Arg], graph: str, audio: str) -> Loudness | None:
    """Run the first pass and return its measurement, or None if the audio is
    too quiet to measure (parse_loudness).

    inputs are ffmpeg's input options and inputs, and graph a -filter_complex
    graph whose stream labelled audio comes out of measure_filter. Raises
    FFmpegError if ffmpeg fails or reports no valid measurement.
    """
    args = [*inputs, "-filter_complex", graph, "-map", audio, "-f", "null", "-"]
    stderr = run_ffmpeg(args, loglevel="info").stderr.decode(errors="replace")
    try:
        loudness = parse_loudness(stderr)
    except ValueError as exc:
        command = [ffmpeg_bin(), *(str(arg) for arg in args)]
        raise FFmpegError(str(exc), command=command, stderr=stderr) from exc
    logger.debug("loudnorm measured %s", loudness)
    return loudness


def _targets(target_lufs: float) -> str:
    """Return loudnorm's target options for target_lufs."""
    return f"i={target_lufs:g}:lra={LOUDNESS_RANGE_LU:g}:tp={TRUE_PEAK_DBTP:g}"
