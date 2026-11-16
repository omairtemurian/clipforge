"""Stored features of style references for the recipe tests (tests only):
the JSON shape analyze_reference_media dumps, with a few numbers set."""

from typing import Any


def features(
    cuts: float, shot: float, luma: float, bpm: float | None, color: str
) -> dict[str, Any]:
    """The stored features of a 30 s reference (as analyze_reference_media
    dumps them) with cuts per minute, median shot, mean luma, music BPM and
    caption color; the rest is fixed."""
    return {
        "video": {
            "duration": 30.0,
            "fps": 30,
            "cuts": {"cuts": [1.0], "per_minute": cuts},
            "color": {
                "mean_luma": luma,
                "contrast": 0.2,
                "saturation": 0.1,
                "bw_share": 0.0,
                "bw_spans": [],
            },
            "flashes": {"flashes": [], "per_minute": 4.0},
        },
        "rhythm": {
            "cuts_per_minute": cuts,
            "median_shot_s": shot,
            "cuts_on_beat": 0.5,
            "zooms_on_beat": None,
        },
        "motion": {
            "punches": {"count": 3, "per_minute": 6.0, "amplitude": 0.15},
            "ramps": {"count": 0, "per_minute": 0.0, "amplitude": None},
            "shakes": {"count": 0, "per_minute": 0.0, "amplitude": None},
        },
        "look": {"vignette": 0.3, "grain": 0.05},
        "glitches": {"splits": [], "spikes": [], "per_minute": 0.0},
        "captions": {
            "frames": 60,
            "text_share": 0.9,
            "lines": 40,
            "words_per_line": 2.0,
            "size_ratio": 0.06,
            "position_x": 0.5,
            "position_y": 0.7,
            "color": color,
            "uppercase_ratio": 1.0,
        },
        "audio": {
            "speech_share": 0.4,
            "music_share": 0.8,
            "has_music": True,
            "bpm": bpm,
            "loudness_curve": [-14.0],
            "drops": [10.0, 20.0],
            "silence_before_drop": 1,
            "sfx_onsets": [],
            "sfx_per_minute": 2.0,
        },
        "structure": {
            "time_to_first_effect": 0.4,
            "first_effect": "cut",
            "hook_s": 1.5,
            "effect_density": [3, 5, 4, 2, 6, 4],
            "ending": "loop",
            "ending_distance": 0.1,
        },
    }


REFS = [
    features(30.0, 2.0, 0.30, 140.0, "#ffffff"),
    features(42.0, 1.4, 0.24, None, "#ffd000"),
    features(18.0, 3.1, 0.36, 150.0, "#f0e000"),
]
