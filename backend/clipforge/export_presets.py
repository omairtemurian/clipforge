"""Export sizes and platform presets (SPEC-v2 3.9).

An export is a clip rendered at a chosen resolution, never above its source
(export_size), and optionally checked against a platform's limits
(ExportPreset, check_export). The limits are copied from each platform's
official documentation; docs/decisions.md records the page and the date it
was read, and each preset carries them too (source_url, checked).

Pure helpers: the only clipforge imports are the aspect sizes and the center
crop that sizes a frame from the source.
"""

from dataclasses import dataclass
from fractions import Fraction

from clipforge.aspect import aspect_size
from clipforge.pipeline.render import center_crop

# Resolution choices (the frame's shorter side, in pixels); None is the
# largest the source allows. "2160p" is 3840x2160 for 16:9 and 2160x3840 for
# 9:16: 4K.
RESOLUTIONS: dict[str, int | None] = {
    "source": None,
    "2160p": 2160,
    "1440p": 1440,
    "1080p": 1080,
    "720p": 720,
}
GB = 1000**3
MB = 1000**2


@dataclass(frozen=True)
class ExportPreset:
    """A platform's limits for the video of a post.

    max_duration_s and max_bytes are the longest and largest file that the
    platform takes; min_duration_s the shortest. max_width, max_height and
    max_short_side bound the frame in pixels (None: no limit). ratio is the
    (narrowest, widest) width / height that it takes. note says what the
    numbers cover, source_url is the official page they come from and
    checked the date it was read.
    """

    id: str
    label: str
    max_duration_s: float
    max_bytes: int
    min_duration_s: float = 0.0
    max_width: int | None = None
    max_height: int | None = None
    max_short_side: int | None = None
    min_side: int | None = None
    ratio: tuple[Fraction, Fraction] = (Fraction(0), Fraction(1000))
    note: str = ""
    source_url: str = ""
    checked: str = ""


PRESETS: dict[str, ExportPreset] = {
    preset.id: preset
    for preset in (
        ExportPreset(
            id="shorts",
            label="YouTube Shorts",
            max_duration_s=180,
            max_bytes=256 * GB,
            ratio=(Fraction(0), Fraction(1)),
            note=(
                "Up to 3 minutes, square or vertical; a wider video is a "
                "regular video. Files up to 256 GB or 12 hours."
            ),
            source_url="https://support.google.com/youtube/answer/15424877",
            checked="2026-11-02",
        ),
        ExportPreset(
            id="tiktok",
            label="TikTok",
            max_duration_s=600,
            max_bytes=4 * GB,
            max_width=4096,
            max_height=4096,
            min_side=360,
            note=(
                "Every creator posts 3 minutes; the API takes up to 10, but "
                "the account's own limit (creator_info max_video_post_duration_sec) "
                "decides. 360 to 4096 pixels a side, 4 GB."
            ),
            source_url=(
                "https://developers.tiktok.com/docs/en/"
                "content-posting-api-media-transfer-guide"
            ),
            checked="2026-11-02",
        ),
        ExportPreset(
            id="reels",
            label="Instagram Reels",
            max_duration_s=900,
            max_bytes=300 * MB,
            min_duration_s=3,
            max_width=1920,
            ratio=(Fraction(1, 100), Fraction(10)),
            note="3 seconds to 15 minutes, 300 MB, at most 1920 pixels wide.",
            source_url=(
                "https://developers.facebook.com/documentation/"
                "instagram-platform/instagram-graph-api/reference/ig-user/media"
            ),
            checked="2026-11-02",
        ),
        ExportPreset(
            id="linkedin",
            label="LinkedIn",
            max_duration_s=1800,
            max_bytes=500 * MB,
            min_duration_s=3,
            note="3 seconds to 30 minutes, 75 KB to 500 MB, MP4.",
            source_url=(
                "https://learn.microsoft.com/en-us/linkedin/marketing/"
                "community-management/shares/videos-api"
            ),
            checked="2026-11-02",
        ),
        ExportPreset(
            id="x",
            label="X",
            max_duration_s=1200,
            max_bytes=8 * GB,
            min_duration_s=0.5,
            max_width=1280,
            max_height=1280,
            max_short_side=720,
            ratio=(Fraction(1, 3), Fraction(3)),
            note=(
                "A default account's Post video: 20 minutes, 8 GB (Premium: "
                "125 minutes, 16 GB). 720p is what a default account plays."
            ),
            source_url="https://docs.x.com/x-api/media/quickstart/best-practices",
            checked="2026-11-02",
        ),
    )
}


def get_preset(preset_id: str) -> ExportPreset:
    """Return the preset preset_id; raises ValueError if there is none."""
    try:
        return PRESETS[preset_id]
    except KeyError:
        raise ValueError(
            f"unknown export preset {preset_id!r}; use one of {', '.join(PRESETS)}"
        ) from None


def check_resolution(resolution: str) -> int | None:
    """Return the shorter side in pixels that resolution (a RESOLUTIONS key)
    asks for, None for "source"; raises ValueError for any other value."""
    if resolution not in RESOLUTIONS:
        raise ValueError(
            f"unknown resolution {resolution!r}; use one of {', '.join(RESOLUTIONS)}"
        )
    return RESOLUTIONS[resolution]


def export_size(
    aspect: str,
    source: tuple[int, int],
    resolution: str = "source",
    preset: ExportPreset | None = None,
) -> tuple[int, int]:
    """Return the (width, height) of an export of aspect from a source video
    of (width, height) pixels.

    The frame has the shape of the aspect's size (aspect.aspect_size) and is
    the largest of that shape that fits the center crop of the source (so
    nothing is scaled up), whose shorter side is at most the resolution's and
    that fits the preset's bounds. Both sides are even, as yuv420p needs.
    """
    base_w, base_h = aspect_size(aspect)
    crop = center_crop(source[0], source[1], base_w, base_h)
    scale = min(Fraction(crop.width, base_w), Fraction(crop.height, base_h))
    short = check_resolution(resolution)
    bounds = [(short, min(base_w, base_h))]
    if preset is not None:
        bounds += [
            (preset.max_width, base_w),
            (preset.max_height, base_h),
            (preset.max_short_side, min(base_w, base_h)),
        ]
    for limit, side in bounds:
        if limit is not None:
            scale = min(scale, Fraction(limit, side))
    return max(_even(base_w * scale), 2), max(_even(base_h * scale), 2)


def check_export(
    preset: ExportPreset, size: tuple[int, int], duration: float, file_bytes: int
) -> list[str]:
    """Return what keeps a file of size (width, height) pixels, duration
    seconds and file_bytes bytes from being posted as preset says; empty if
    it fits."""
    width, height = size
    problems = []
    if duration > preset.max_duration_s:
        problems.append(
            f"{duration:.1f} s is longer than the {preset.max_duration_s:g} s "
            f"{preset.label} takes"
        )
    if duration < preset.min_duration_s:
        problems.append(
            f"{duration:.1f} s is shorter than the {preset.min_duration_s:g} s "
            f"{preset.label} needs"
        )
    if file_bytes > preset.max_bytes:
        problems.append(
            f"{file_bytes / MB:.0f} MB is larger than the "
            f"{preset.max_bytes / MB:.0f} MB {preset.label} takes"
        )
    narrow, wide = preset.ratio
    if not narrow <= Fraction(width, height) <= wide:
        problems.append(f"a {width}x{height} frame has a shape {preset.label} refuses")
    if preset.min_side is not None and min(width, height) < preset.min_side:
        problems.append(
            f"{width}x{height} is under the {preset.min_side} pixels a side "
            f"{preset.label} needs"
        )
    return problems


def _even(value: Fraction) -> int:
    """Round value down to an even whole number."""
    whole = int(value)
    return whole - whole % 2
