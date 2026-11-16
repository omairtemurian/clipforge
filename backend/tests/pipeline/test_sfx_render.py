"""Pipeline tests of the Pro Edit SFX (SPEC-v3 3.3, TASK-214): rendered with
ffmpeg on a silent 6 s source, every planned SFX is an RMS spike on its
frame, a stretched whoosh lasts its motion, the SFX duck under speech, and
the whooshes the engine places stay clear of punchline words."""

from pathlib import Path

import pytest
from clipforge.ffmpeg import run_ffmpeg
from clipforge.models import EdlItem
from clipforge.pipeline.sfx import SFX_DIR
from clipforge.proedit.audio import sfx_mix
from clipforge.proedit.audio.sfx_place import place_whooshes
from clipforge.proedit.audio.sounds import ffmpeg_has
from clipforge.proedit.snap import PlanTiming
from edl_fakes import item, plan
from proedit_render import CLIP
from proedit_sound import (
    FPS,
    RATE,
    Samples,
    audible_span,
    decoded,
    levels_db,
    onset_frame,
    render_sound,
    silent_video,
)


@pytest.fixture(scope="module")
def silent(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A 6 s 1280x720 30 fps still video whose sound is digital silence."""
    return silent_video(tmp_path_factory.mktemp("sfx") / "silent.mp4")


@pytest.fixture(scope="module")
def burst(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A library sound with sharp edges: 0.5 s of steady noise, 44.1 kHz
    stereo (so the renderer resamples it)."""
    sound = tmp_path_factory.mktemp("sfx") / "burst.flac"
    run_ffmpeg(
        ["-f", "lavfi", "-i", "anoisesrc=r=44100:a=0.4:d=0.5:seed=5"]
        + ["-ac", "2", "-c:a", "flac", sound]
    )
    return sound


def sfx(id: int, start: float, end: float, asset: str, **params: object) -> EdlItem:
    return item(id, "sfx", start, end, params={"asset": asset, **params})


def render(
    tmp_path: Path,
    source: Path,
    items: list[EdlItem],
    library: dict[str, Path] | None = None,
    speech: tuple[tuple[float, float], ...] = (),
) -> Samples:
    """Render CLIP of source with items and return its sound, mono at RATE."""
    return render_sound(tmp_path, source, items, library, speech, name="sfx")


def test_each_planned_sfx_is_an_rms_spike_on_its_frame(
    silent: Path, burst: Path, tmp_path: Path
) -> None:
    items = [
        sfx(1, 0.5, 0.7, "pop_bubble"),
        sfx(2, 1.0, 1.1, "tick_click.flac", gain_db=0),
        sfx(3, 1.5, 2.0, "ding_bell"),
        sfx(4, 7 / 3, 3.0, "impact_boom", pitch_semitones=-3),
        sfx(5, 3.3, 3.8, "9", pitch_semitones=2, fit="stretch"),
    ]
    sound = render(tmp_path, silent, items, {"9": burst})
    assert len(sound) / RATE == pytest.approx(CLIP.end - CLIP.start, abs=0.05)
    for planned in items:
        start = round(planned.t_start * FPS)
        found = onset_frame(sound, start - 6, round(planned.t_end * FPS))
        assert abs(found - start) <= 1, planned


@pytest.mark.parametrize(("rubberband", "tolerance"), [(True, 0.02), (False, 0.05)])
def test_a_stretched_sound_lasts_its_item(
    silent: Path,
    burst: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rubberband: bool,
    tolerance: float,
) -> None:
    # The 0.5 s burst pitched up (shorter) then stretched to 0.8 s, and
    # pitched down (longer) then squeezed to 0.3 s; atempo (no rubberband
    # in the build) blurs the ends by a few tens of milliseconds.
    if rubberband and not ffmpeg_has("rubberband"):
        pytest.skip("this ffmpeg build has no rubberband filter")
    monkeypatch.setattr(sfx_mix, "ffmpeg_has", lambda name: rubberband)
    items = [
        sfx(1, 1.0, 1.8, "9", pitch_semitones=2, fit="stretch"),
        sfx(2, 2.5, 2.8, "9", pitch_semitones=-2, fit="stretch"),
    ]
    sound = render(tmp_path, silent, items, {"9": burst})
    for planned in items:
        part = sound[round((planned.t_start - 0.2) * RATE) : round(3.5 * RATE)]
        part = part[: round((planned.t_end - planned.t_start + 0.4) * RATE)]
        first, last = audible_span(part)
        assert first == pytest.approx(0.2, abs=0.02)
        length = planned.t_end - planned.t_start
        assert last - first == pytest.approx(length, abs=tolerance)


def test_the_sfx_duck_under_speech(silent: Path, burst: Path, tmp_path: Path) -> None:
    items = [sfx(1, 1.0, 1.4, "9"), sfx(2, 2.3, 2.7, "9")]
    sound = render(tmp_path, silent, items, {"9": burst}, speech=((2.0, 3.0),))
    alone = levels_db(sound[round(1.1 * RATE) : round(1.3 * RATE)], 9600)[0]
    spoken = levels_db(sound[round(2.4 * RATE) : round(2.6 * RATE)], 9600)[0]
    assert alone - spoken == pytest.approx(6.0, abs=0.5)


def test_placed_whooshes_last_their_motion_and_miss_the_punchline(
    silent: Path, tmp_path: Path
) -> None:
    # A push-in over 0.4-1.2 s and an instant punch at 3.0 s on a punchline
    # word (3.0-3.4 s): the punch's whoosh moves before the word (the two
    # whooshes start over 2 s apart, the pro SFX budget).
    visual = [
        item(1, "zoom_push", 0.4, 1.2, params={"center": "frame"}),
        item(2, "zoom_punch", 3.0, 3.5, params={"center": "frame"}),
    ]
    timing = PlanTiming(FPS, 4.0, punchlines=((3.0, 3.4),))
    placed = place_whooshes(plan(visual, "pro"), timing)
    whooshes = [i for i in placed.plan.items if i.kind == "sfx"]
    assert [(w.t_start, w.t_end) for w in whooshes] == [
        (0.4, 1.2),
        (80 / 30, 89 / 30),
    ]
    sound = render(tmp_path, silent, placed.plan.items)
    for whoosh in whooshes:
        source = decoded(SFX_DIR / f"{whoosh.params['asset']}.flac")
        head, tail = audible_span(source)
        share = (tail - head) / (len(source) / RATE)
        part = sound[round(whoosh.t_start * RATE) : round(whoosh.t_end * RATE)]
        first, last = audible_span(part)
        length = whoosh.t_end - whoosh.t_start
        assert last - first == pytest.approx(share * length, abs=0.02)
    word = levels_db(sound[round(3.0 * RATE) : round(3.4 * RATE)], RATE // FPS)
    assert word.max() < -70
