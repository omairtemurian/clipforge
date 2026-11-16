"""The numbers a style recipe aims for (SPEC-v3 4.4) and how each is read
from the features of a video (style/analyze.ReferenceFeatures as JSON data,
the same for a reference and for a measured Pro Edit).

Each metric is one number per video, or None when the video does not have
it (no audio, no captions read, no beat grid, no zoom to take an amplitude
from). Rates are per minute of video; shares are 0..1. The slider bounds
are where the recipe editor's sliders end, not limits of the features.
"""

import statistics
from collections.abc import Callable
from typing import Any

from clipforge.models import StyleMetric, StyleMetricGroup

Features = dict[str, Any]
Reader = Callable[[Features], float | None]


def _at(*path: str) -> Reader:
    """Return a reader of the number at path in the features."""

    def read(features: Features) -> float | None:
        node: Any = features
        for key in path:
            if not isinstance(node, dict) or node.get(key) is None:
                return None
            node = node[key]
        return float(node) if isinstance(node, int | float) else None

    return read


def _drops_per_minute(features: Features) -> float | None:
    audio = features.get("audio")
    duration = (features.get("video") or {}).get("duration") or 0
    if not audio or duration <= 0:
        return None
    return len(audio.get("drops") or []) / (duration / 60)


def _effects_per_window(features: Features) -> float | None:
    density = (features.get("structure") or {}).get("effect_density") or []
    return float(statistics.mean(density)) if density else None


def _loop_ending(features: Features) -> float | None:
    ending = (features.get("structure") or {}).get("ending")
    return None if ending is None else float(ending == "loop")


def _metric(
    key: str,
    label: str,
    unit: str,
    group: StyleMetricGroup,
    bounds: tuple[float, float, float],
    tolerance: float,
) -> StyleMetric:
    """Return the metric key; bounds are its slider's min, max and step."""
    low, high, step = bounds
    return StyleMetric(
        key=key,
        label=label,
        unit=unit,
        group=group,
        min=low,
        max=high,
        step=step,
        tolerance=tolerance,
    )


METRICS: list[StyleMetric] = [
    _metric("cuts_per_minute", "Cuts", "/min", "rhythm", (0, 120, 1), 6),
    _metric("median_shot_s", "Shot length", "s", "rhythm", (0, 10, 0.1), 0.5),
    _metric("cuts_on_beat", "Cuts on the beat", "share", "rhythm", (0, 1, 0.01), 0.15),
    _metric(
        "zooms_on_beat", "Zooms on the beat", "share", "rhythm", (0, 1, 0.01), 0.15
    ),
    _metric("punches_per_minute", "Zoom punches", "/min", "motion", (0, 60, 0.5), 3),
    _metric("punch_amplitude", "Punch strength", "scale", "motion", (0, 1, 0.01), 0.05),
    _metric("ramps_per_minute", "Zoom ramps", "/min", "motion", (0, 30, 0.5), 2),
    _metric("shakes_per_minute", "Shakes", "/min", "motion", (0, 30, 0.5), 2),
    _metric("mean_luma", "Brightness", "share", "look", (0, 1, 0.01), 0.05),
    _metric("contrast", "Contrast", "share", "look", (0, 0.5, 0.01), 0.03),
    _metric("saturation", "Saturation", "share", "look", (0, 1, 0.01), 0.05),
    _metric("bw_share", "Black & white", "share", "look", (0, 1, 0.01), 0.1),
    _metric("vignette", "Vignette", "share", "look", (0, 1, 0.01), 0.1),
    _metric("grain", "Grain", "share", "look", (0, 1, 0.01), 0.05),
    _metric("flashes_per_minute", "Flashes", "/min", "effects", (0, 60, 0.5), 3),
    _metric("glitches_per_minute", "Glitches", "/min", "effects", (0, 60, 0.5), 3),
    _metric(
        "caption_words_per_line",
        "Caption words per line",
        "words",
        "captions",
        (0, 10, 0.5),
        1,
    ),
    _metric(
        "caption_size", "Caption size", "of height", "captions", (0, 0.3, 0.005), 0.02
    ),
    _metric(
        "caption_position_y",
        "Caption height",
        "from top",
        "captions",
        (0, 1, 0.01),
        0.1,
    ),
    _metric(
        "caption_uppercase", "Caption uppercase", "share", "captions", (0, 1, 0.01), 0.2
    ),
    _metric("music_share", "Music", "share", "audio", (0, 1, 0.01), 0.15),
    _metric("bpm", "Music tempo", "BPM", "audio", (40, 220, 1), 8),
    _metric("drops_per_minute", "Drops", "/min", "audio", (0, 20, 0.5), 1),
    _metric("sfx_per_minute", "Sound effects", "/min", "audio", (0, 60, 0.5), 3),
    _metric(
        "time_to_first_effect", "First effect", "s", "structure", (0, 10, 0.1), 0.5
    ),
    _metric("hook_s", "Hook length", "s", "structure", (0, 15, 0.1), 0.5),
    _metric(
        "effects_per_window", "Effects per 5 s", "effects", "structure", (0, 20, 0.5), 1
    ),
    _metric("loop_ending", "Loop ending", "share", "structure", (0, 1, 0.5), 0.5),
]
METRIC_BY_KEY: dict[str, StyleMetric] = {metric.key: metric for metric in METRICS}
_READERS: dict[str, Reader] = {
    "cuts_per_minute": _at("rhythm", "cuts_per_minute"),
    "median_shot_s": _at("rhythm", "median_shot_s"),
    "cuts_on_beat": _at("rhythm", "cuts_on_beat"),
    "zooms_on_beat": _at("rhythm", "zooms_on_beat"),
    "punches_per_minute": _at("motion", "punches", "per_minute"),
    "punch_amplitude": _at("motion", "punches", "amplitude"),
    "ramps_per_minute": _at("motion", "ramps", "per_minute"),
    "shakes_per_minute": _at("motion", "shakes", "per_minute"),
    "mean_luma": _at("video", "color", "mean_luma"),
    "contrast": _at("video", "color", "contrast"),
    "saturation": _at("video", "color", "saturation"),
    "bw_share": _at("video", "color", "bw_share"),
    "vignette": _at("look", "vignette"),
    "grain": _at("look", "grain"),
    "flashes_per_minute": _at("video", "flashes", "per_minute"),
    "glitches_per_minute": _at("glitches", "per_minute"),
    "caption_words_per_line": _at("captions", "words_per_line"),
    "caption_size": _at("captions", "size_ratio"),
    "caption_position_y": _at("captions", "position_y"),
    "caption_uppercase": _at("captions", "uppercase_ratio"),
    "music_share": _at("audio", "music_share"),
    "bpm": _at("audio", "bpm"),
    "drops_per_minute": _drops_per_minute,
    "sfx_per_minute": _at("audio", "sfx_per_minute"),
    "time_to_first_effect": _at("structure", "time_to_first_effect"),
    "hook_s": _at("structure", "hook_s"),
    "effects_per_window": _effects_per_window,
    "loop_ending": _loop_ending,
}


def metric_values(features: Features) -> dict[str, float]:
    """Return the value of each metric the features have, by key, in the
    order of METRICS."""
    values = {key: read(features) for key, read in _READERS.items()}
    return {key: value for key, value in values.items() if value is not None}


def caption_color(features: Features) -> str | None:
    """Return the caption fill color of the features (#rrggbb), if any."""
    color = (features.get("captions") or {}).get("color")
    return color if isinstance(color, str) else None
