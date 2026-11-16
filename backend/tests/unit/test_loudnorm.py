"""Unit tests of the two-pass loudness normalization: loudnorm's report, the
filters of both passes and the first pass run on generated audio."""

import math

import pytest
from clipforge.ffmpeg import FFmpegError, ffmpeg_bin
from clipforge.pipeline.loudnorm import (
    Loudness,
    measure_filter,
    measure_loudness,
    normalize_filter,
    parse_loudness,
)

# What ffmpeg 9.0.2 logs at the info level around loudnorm's report on clip A
# of the fixture after its cuts; the metadata holds braces of its own.
REPORT = """\
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'sample.mp4':
  Metadata:
    comment         : {"not": "the report"}
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 48000 Hz, mono
[Parsed_loudnorm_8 @ 0x7a9ac69880] \n{
\t"input_i" : "-22.76",
\t"input_tp" : "-0.33",
\t"input_lra" : "13.90",
\t"input_thresh" : "-33.19",
\t"output_i" : "-15.30",
\t"output_tp" : "-2.00",
\t"output_lra" : "3.80",
\t"output_thresh" : "-25.53",
\t"normalization_type" : "dynamic",
\t"target_offset" : "1.30"
}
[out#0/null @ 0x7a9ad28300] video:0KiB audio:5799KiB subtitle:0KiB
"""
MEASURED = Loudness(-22.76, -0.33, 13.9, -33.19, 1.3)
TONE = ["-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000:duration=4"]


def test_parse_loudness_reads_the_report_after_loudnorms_prefix() -> None:
    assert parse_loudness(REPORT) == MEASURED


def test_parse_loudness_reads_the_last_report() -> None:
    louder = REPORT.replace('"-22.76"', '"-12.50"')

    assert parse_loudness(REPORT + louder) == Loudness(-12.5, -0.33, 13.9, -33.19, 1.3)


def test_parse_loudness_of_silence_is_none() -> None:
    silence = (
        REPORT.replace('"-22.76"', '"-inf"')
        .replace('"-0.33"', '"-inf"')
        .replace('"1.30"', '"inf"')
    )

    assert parse_loudness(silence) is None


@pytest.mark.parametrize(
    "stderr",
    [
        "",
        REPORT.split("[Parsed_loudnorm_8")[0],
        REPORT.replace("{\n\t", "\n\t"),
        REPORT.replace('\t"input_lra" : "13.90",\n', ""),
        REPORT.replace('"13.90"', '"loud"'),
        '[Parsed_loudnorm_0 @ 0x1] {"input_i": [1]}',
    ],
    ids=["empty", "no-report", "no-json", "missing-key", "not-a-number", "list"],
)
def test_parse_loudness_rejects_a_missing_or_broken_report(stderr: str) -> None:
    with pytest.raises(ValueError, match="loudnorm"):
        parse_loudness(stderr)


def test_measure_filter_reports_json_for_the_target() -> None:
    assert measure_filter(-14) == "loudnorm=i=-14:lra=7:tp=-2:print_format=json"
    assert measure_filter(-16.5).startswith("loudnorm=i=-16.5:")


def test_normalize_filter_is_linear_with_the_measurement_then_48k() -> None:
    assert normalize_filter(-14, MEASURED) == (
        "loudnorm=i=-14:lra=7:tp=-2:measured_i=-22.76:measured_tp=-0.33:"
        "measured_lra=13.90:measured_thresh=-33.19:offset=1.30:linear=true,"
        "aresample=48000,asetpts=N/SR/TB+STARTPTS"
    )


def test_normalize_filter_keeps_values_within_loudnorms_ranges() -> None:
    wild = Loudness(3.0, -120.0, 150.0, 5.0, -150.0)

    assert (
        "measured_i=0.00:measured_tp=-99.00:measured_lra=99.00:"
        "measured_thresh=0.00:offset=-99.00:"
    ) in normalize_filter(-14, wild)


def test_measure_loudness_measures_a_tone() -> None:
    loudness = measure_loudness(TONE, f"[0:a:0]{measure_filter(-14)}[a]", "[a]")

    # lavfi's sine has amplitude 1/8: a peak of -18 dBFS.
    assert loudness is not None
    assert loudness.true_peak == pytest.approx(-18.1, abs=0.3)
    assert -24 < loudness.integrated < -18
    assert all(math.isfinite(value) for value in (loudness.offset, loudness.threshold))


def test_measure_loudness_of_silence_is_none() -> None:
    silence = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=2"]

    assert measure_loudness(silence, f"[0:a:0]{measure_filter(-14)}[a]", "[a]") is None


def test_measure_loudness_without_a_report_raises_ffmpeg_error() -> None:
    with pytest.raises(FFmpegError, match="loudnorm reported no measurement") as info:
        measure_loudness(TONE, "[0:a:0]anull[a]", "[a]")

    assert info.value.command[:3] == [ffmpeg_bin(), "-f", "lavfi"]
