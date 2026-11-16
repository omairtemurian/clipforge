"""Captions burnt into rendered clips (SPEC 6.9, 6.11): the pixels that they
change and when, the ffprobe checks of a captioned clip, the bundled fonts
that libass draws each template with, and file names that the filter graph
has to escape."""

import re
import shutil
from pathlib import Path

import numpy as np
import pytest
from builders import make_clip
from clipforge.captions_templates import get_template, load_templates
from clipforge.config import RenderSettings
from clipforge.ffmpeg import FFmpegError, probe_media, run_ffmpeg
from clipforge.fonts import EMOJI_FONT, FONTS_DIR
from clipforge.models import CropPlan, FaceBox
from clipforge.pipeline.captions import write_captions
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.pipeline.render import (
    SIZES,
    render_clip,
    render_problems,
)
from clipforge.pipeline.render_graph import subtitles_filter
from clipforge.pipeline.step import TRANSCRIPT
from fakes import FIXTURES
from frames import frame_at

# Clip 1 of the fixture, 0.5-8.5 s, in karaoke_bold: its hook shows at the
# top for 2.5 s and its captions in the lower third, where (in clip times)
# "everyone" is active from 0.29 s, "the" from 2.95 s, "body." until 5.55 s
# and "um," from 6.25 s.
CLIP = ClipSpan(1, 0.5, 8.5)
FPS = RenderSettings().fps
HOOK = "My body had one question for my yoga teacher"
# Bands of the frame, from and to a fraction of its height.
BANDS = {
    "hook": (0.09, 0.2),
    "middle": (0.4, 0.6),
    "caption": (0.7, 0.78),
    "bottom": (0.78, 1.0),
}
# The time of a frame of the clip and the bands that captions draw on in it.
DRAWN = {
    "hook and caption": (1.0, {"hook", "caption"}),
    "caption after the hook": (3.0, {"caption"}),
    "pause between words": (5.9, set()),
}
# The font that libass selects for each font name of the caption templates.
SELECTED = {
    "Montserrat ExtraBold": "Montserrat-ExtraBold",
    "Inter Bold": "Inter-Bold",
    EMOJI_FONT: "NotoEmoji-Regular",
    "Poppins Black": "Poppins-Black",
    "Anton": "Anton-Regular",
    "Bebas Neue": "BebasNeue-Regular",
    "Bangers": "Bangers-Regular",
    "Archivo Black": "ArchivoBlack-Regular",
    "Lilita One": "LilitaOne",
    "Titan One": "TitanOne",
    "Bungee": "Bungee-Regular",
    "Passion One Black": "PassionOne-Black",
    "Righteous": "Righteous-Regular",
    "Staatliches": "Staatliches-Regular",
    "Luckiest Guy": "LuckiestGuy-Regular",
    "Permanent Marker": "PermanentMarker-Regular",
}
FONTSELECT = re.compile(r"fontselect: \((.+?), \d+, \d+\) -> (.+?),")


@pytest.fixture(scope="module")
def job(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A job directory with the fixture's transcript."""
    job = tmp_path_factory.mktemp("job")
    shutil.copy(FIXTURES / "transcript.json", job / TRANSCRIPT)
    return job


@pytest.fixture(scope="module")
def plan() -> CropPlan:
    """The crop plan of CLIP at 9:16, with no faces: a centered window."""
    no_faces: list[list[FaceBox]] = [[] for _ in sample_times(CLIP.start, CLIP.end)]
    return plan_crop(CLIP, "9:16", (1280, 720), no_faces, [])


@pytest.fixture(scope="module")
def renders(
    sample_mp4: Path, job: Path, plan: CropPlan, render_settings: RenderSettings
) -> dict[str, Path]:
    """CLIP rendered at 9:16 in fill: "plain" without captions and
    "captioned" with them."""
    clip = make_clip(
        "karaoke_bold", id=1, start=CLIP.start, end=CLIP.end, hook_text=HOOK
    )
    captions = write_captions(job, clip, SIZES["9:16"], FPS)
    return {
        name: render_clip(
            sample_mp4,
            job / f"{name}.mp4",
            CLIP.start,
            CLIP.end,
            plan,
            "fill",
            render_settings,
            captions=ass,
        )
        for name, ass in (("plain", None), ("captioned", captions))
    }


def changes(renders: dict[str, Path], time_s: float) -> dict[str, float]:
    """Return the fraction of the pixels of each band that the captions
    changed in the frame at time_s: by more than 64 in a channel, while
    encoding alone changes a pixel by less than 20."""
    plain, captioned = (
        frame_at(renders[name], time_s).astype(int) for name in ("plain", "captioned")
    )
    changed = np.abs(plain - captioned).max(axis=2) > 64
    height = len(changed)
    return {
        band: float(changed[round(top * height) : round(bottom * height)].mean())
        for band, (top, bottom) in BANDS.items()
    }


def libass_log(captions: Path, fonts_dir: Path = FONTS_DIR) -> str:
    """Return what libass logs while it draws captions, with the fonts in
    fonts_dir, on a blank 1080x1920 video of 4 s at 4 frames a second."""
    result = run_ffmpeg(
        ["-f", "lavfi", "-i", "color=size=1080x1920:rate=4:duration=4"]
        + ["-vf", subtitles_filter(captions, fonts_dir), "-f", "null", "-"],
        loglevel="info",
    )
    return result.stderr.decode()


@pytest.mark.parametrize(("time_s", "drawn"), DRAWN.values(), ids=list(DRAWN))
def test_captions_change_the_frame_where_and_while_they_show(
    renders: dict[str, Path], time_s: float, drawn: set[str]
) -> None:
    fractions = changes(renders, time_s)

    assert {band for band, part in fractions.items() if part > 0.02} == drawn
    assert all(fractions[band] == 0.0 for band in BANDS.keys() - drawn), fractions


def test_a_captioned_clip_passes_the_ffprobe_checks(renders: dict[str, Path]) -> None:
    info = probe_media(renders["captioned"])

    assert render_problems(info, SIZES["9:16"], CLIP.end - CLIP.start) == []
    assert info.fps == 30


@pytest.mark.parametrize("name", sorted(load_templates()))
def test_libass_draws_each_template_with_its_bundled_fonts(
    name: str, job: Path
) -> None:
    # In 30-34 s of the fixture, "cheese." has an emoji (emoji_map.yaml).
    captions = write_captions(
        job, make_clip(name, start=30.0, end=34.0), (1080, 1920), FPS
    )
    template = get_template(name)

    log = libass_log(captions)

    fonts = [template.font, EMOJI_FONT] if template.emoji else [template.font]
    assert dict(FONTSELECT.findall(log)) == {font: SELECTED[font] for font in fonts}
    assert "Glyph 0x" not in log


def test_the_subtitles_filter_reads_any_file_name(job: Path, tmp_path: Path) -> None:
    clip = make_clip("karaoke_bold", start=0.5, end=4.5)
    weird = tmp_path / "it's [1], a;b=c\\d:e %p"
    fonts = weird / "fo'nts: [x], y;z "
    shutil.copytree(FONTS_DIR, fonts)
    captions = weird / " cap'tions: 7, [x];y.ass"
    shutil.copy(write_captions(job, clip, (1080, 1920), FPS), captions)

    log = libass_log(captions, fonts)

    assert f"Loading font file '{fonts / 'Montserrat-ExtraBold.ttf'}'" in log
    assert dict(FONTSELECT.findall(log)) == {
        "Montserrat ExtraBold": "Montserrat-ExtraBold"
    }


def test_a_clip_whose_captions_are_missing_fails_to_render(
    sample_mp4: Path, plan: CropPlan, tmp_path: Path
) -> None:
    output = tmp_path / "1.mp4"
    missing = tmp_path / "captions_1.ass"

    with pytest.raises(FFmpegError, match=r"Unable to open .*captions_1\.ass"):
        render_clip(
            sample_mp4,
            output,
            CLIP.start,
            CLIP.end,
            plan,
            "fill",
            RenderSettings(),
            captions=missing,
        )

    assert list(tmp_path.iterdir()) == []
