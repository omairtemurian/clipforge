"""The SPEC 5 timing and length rules that a clip candidate must meet.

Curate drops the LLM's candidates that break them (pipeline/curate_select)
and tells the LLM the length ranges in its prompt (pipeline/curate_prompt).
A project may choose several length presets; a candidate fits when its
length fits any of them.
"""

from collections.abc import Sequence

from clipforge.config import Settings
from clipforge.models import ClipCandidate, LengthPreset

# The fixed presets; "auto" and "custom" take their range from the settings.
PRESET_LENGTH_RANGES: dict[LengthPreset, tuple[float, float]] = {
    "lt30": (0.0, 30.0),
    "0_60": (0.0, 60.0),
    "30_60": (30.0, 60.0),
    "60_90": (60.0, 90.0),
    "60_180": (60.0, 180.0),
    "90_180": (90.0, 180.0),
    "180_300": (180.0, 300.0),
    "300_600": (300.0, 600.0),
    "600_900": (600.0, 900.0),
}
# The hashtags of a candidate that no LLM wrote (ClipCandidate needs 3).
DEFAULT_HASHTAGS = ("video", "clip", "shorts")
# The longest clip that "auto" allows: 3 minutes.
AUTO_MAX_S = 180.0


def length_range(
    preset: LengthPreset,
    cfg: Settings,
    custom: tuple[float, float] | None = None,
) -> tuple[float, float]:
    """Return the (min, max) clip length in seconds allowed by a length preset.

    "auto" allows cfg.clip_min_s..AUTO_MAX_S (its prompt asks mostly for
    cfg.clip_min_s..cfg.clip_max_s); "custom" allows the custom range, which
    must then be given. Both bounds are inclusive, except for "lt30", where
    clips must be shorter than 30 seconds.
    """
    if preset == "auto":
        return float(cfg.clip_min_s), AUTO_MAX_S
    if preset == "custom":
        if custom is None:
            raise ValueError("the custom length preset needs a custom range")
        return custom
    return PRESET_LENGTH_RANGES[preset]


def longest_clip(
    presets: Sequence[LengthPreset],
    cfg: Settings,
    custom: tuple[float, float] | None = None,
) -> float:
    """Return the longest clip, in seconds, that any of presets allows."""
    return max(length_range(preset, cfg, custom)[1] for preset in presets)


def fits_preset(
    length: float,
    preset: LengthPreset,
    cfg: Settings,
    custom: tuple[float, float] | None = None,
) -> bool:
    """Whether a clip of length seconds fits a length preset (length_range)."""
    min_s, max_s = length_range(preset, cfg, custom)
    if preset == "lt30":
        return min_s < length < max_s
    return min_s <= length <= max_s


def describe_range(
    preset: LengthPreset,
    cfg: Settings,
    custom: tuple[float, float] | None = None,
) -> str:
    """Return a preset's range as a log reason says it: "30-60s", "under 30s"."""
    min_s, max_s = length_range(preset, cfg, custom)
    return f"under {max_s:g}s" if preset == "lt30" else f"{min_s:g}-{max_s:g}s"


def validate_candidate(
    c: ClipCandidate,
    duration: float,
    presets: Sequence[LengthPreset],
    cfg: Settings,
    custom: tuple[float, float] | None = None,
) -> tuple[bool, str]:
    """Check an LLM clip candidate against the video duration and length presets.

    A candidate is kept when 0 <= start < end <= duration and its length fits
    any of presets (custom is the range of the "custom" preset). Returns
    (True, "") to keep it, or (False, reason) so the caller can drop it and
    log why.
    """
    if c.start < 0:
        return False, f"start {c.start:g}s is negative"
    if c.start >= c.end:
        return False, f"start {c.start:g}s is not before end {c.end:g}s"
    if c.end > duration:
        return False, f"end {c.end:g}s is after the video duration {duration:g}s"

    # Timestamps have millisecond precision; rounding removes float noise at bounds.
    length = round(c.end - c.start, 3)
    if any(fits_preset(length, preset, cfg, custom) for preset in presets):
        return True, ""
    ranges = ", ".join(f"{p} ({describe_range(p, cfg, custom)})" for p in presets)
    return False, f"length {length:g}s is outside the chosen ranges: {ranges}"
