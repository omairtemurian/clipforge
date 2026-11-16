"""Gain envelopes over time spans of a Pro Edit's sound (SPEC-v3 3.3): the
level expression that is 1 in a set of spans and 0 a ramp away from them,
and the filters that lower a sound by it.

`volume` with eval=frame (dips: ducking) evaluates its expression once per
audio frame (1024 samples, about 21 ms), so its ramps are steps of a frame;
`aeval` (gates: silences and effect windows) evaluates it on every sample,
so a gate opens and closes on its sample. A gate's sound is stereo
(GATE_LAYOUT) before and after it: `aeval` with c=same crashes ffmpeg
9.0.2 (SIGSEGV) when its mono output is mixed with a stereo sound, and its
c=stereo output is an unordered "2 channels" layout that the AAC encoder
refuses (docs/decisions.md).
"""

from collections.abc import Sequence

from clipforge.pipeline.layout_parts import balanced_sum

Span = tuple[float, float]
GATE_LAYOUT = "stereo"


def merged_spans(spans: Sequence[Span], gap: float) -> list[Span]:
    """Return spans in order with those less than gap apart joined."""
    merged: list[Span] = []
    for start, end in sorted(spans):
        if merged and start - merged[-1][1] < gap:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def level_expr(spans: Sequence[Span], ramp: float) -> str:
    """Return the expression in t (seconds) that is 1 in spans (apart by at
    least 2 * ramp: merged_spans) and ramps to 0 over ramp outside each;
    the ramps are summed balanced so the expression never nests deep."""
    ramps = [
        f"min(clip((t-{start - ramp:.6f})/{ramp:g},0,1),"
        f"clip(({end + ramp:.6f}-t)/{ramp:g},0,1))"
        for start, end in spans
    ]
    return f"min(1,{balanced_sum(ramps)})"


def dip_filter(spans: Sequence[Span], db: float, ramp: float) -> str:
    """Return the volume filter that lowers a sound by db in spans (ramping
    over ramp on each side, a frame at a time); "" if there are none."""
    if not spans:
        return ""
    drop = 1 - 10 ** (-db / 20)
    return f"volume=volume='1-{drop:.6f}*{level_expr(spans, ramp)}':eval=frame"


def gate_filter(spans: Sequence[Span], ramp: float, inside: bool) -> str:
    """Return the aeval filter that keeps a sound only inside spans (if
    inside) or only outside them, ramping over ramp inside each span's
    edges, on every sample, in stereo; spans must be longer than
    2 * ramp."""
    level = level_expr([(start + ramp, end - ramp) for start, end in spans], ramp)
    gain = level if inside else f"(1-{level})"
    return (
        f"aformat=channel_layouts={GATE_LAYOUT},"
        f"aeval=exprs='val(ch)*{gain}':c={GATE_LAYOUT},"
        f"aformat=channel_layouts={GATE_LAYOUT}"
    )
