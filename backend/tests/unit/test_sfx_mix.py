"""Unit tests of the Pro Edit SFX mix and sound lookup (SPEC-v3 3.3,
TASK-214): the filter strings that pitch, stretch, place and duck each
sound, and how an item's asset names its file."""

from pathlib import Path

import pytest
from clipforge.assets import add_asset
from clipforge.pipeline.sfx import SFX_DIR
from clipforge.proedit.audio import sfx_mix
from clipforge.proedit.audio.sfx_mix import (
    audio_graph,
    duck_filter,
    merged_spans,
    pitch_rate,
    pitched_seconds,
    played_seconds,
    sound_filter,
    tempo_filters,
)
from clipforge.proedit.audio.sounds import (
    bundled_named,
    ffmpeg_has,
    find_sound,
    library_sounds,
    sound_problems,
    sound_seconds,
)
from clipforge.proedit.edl import SfxItem, parse_item
from clipforge.proedit.render.graph import undrawn
from edl_fakes import item
from sqlalchemy import Engine
from sqlmodel import Session

SOUND = Path("/s/w.flac")
AMOVIE = "amovie=filename=/s/w.flac,aresample=48000"


def sfx(
    id: int, start: float, end: float, asset: str = "whoosh_swift", **params: object
) -> SfxItem:
    parsed = parse_item(item(id, "sfx", start, end, params={"asset": asset, **params}))
    assert isinstance(parsed, SfxItem)
    return parsed


def test_pitch_is_a_relabelled_sample_rate() -> None:
    assert [pitch_rate(s) for s in (0, 12, -12, 2)] == [48000, 96000, 24000, 53878]
    assert pitched_seconds(0.5, 12) == 0.25
    assert pitched_seconds(0.5, -12) == 1.0


def test_tempo_is_one_filter_or_a_chain_below_half() -> None:
    assert tempo_filters(1.0) == []
    assert tempo_filters(0.8) == ["atempo=0.800000"]
    assert tempo_filters(3.0) == ["atempo=3.000000"]
    assert tempo_filters(0.2) == ["atempo=0.5", "atempo=0.5", "atempo=0.800000"]
    assert tempo_filters(0.2, rubberband=True) == ["rubberband=tempo=0.200000"]


def test_a_stretched_sound_is_pitched_then_stretched_to_the_item() -> None:
    whoosh = sfx(3, 1.0, 1.8, gain_db=-8, pitch_semitones=-12, fit="stretch")
    assert sound_filter(whoosh, SOUND, 0.5, "[a]") == (
        f"{AMOVIE},asetrate=24000,aresample=48000,atempo=1.250000,"
        "atrim=duration=0.800000,apad=whole_dur=0.800000,"
        "volume=-8dB,adelay=delays=1000.000:all=1[a]"
    )
    assert sound_filter(whoosh, SOUND, 0.5, "[a]", rubberband=True).startswith(
        f"{AMOVIE},asetrate=24000,aresample=48000,rubberband=tempo=1.250000,atrim"
    )
    assert played_seconds(whoosh, 0.5) == pytest.approx(0.8)


def test_a_natural_sound_plays_its_length_or_fades_at_the_item_end() -> None:
    short = sfx(1, 2.5, 3.5, gain_db=0)
    assert sound_filter(short, SOUND, 0.5, "[b]") == (
        f"{AMOVIE},volume=0dB,adelay=delays=2500.000:all=1[b]"
    )
    assert played_seconds(short, 0.5) == 0.5
    cut = sfx(1, 1 / 30, 0.2)
    assert sound_filter(cut, SOUND, 0.5, "[c]") == (
        f"{AMOVIE},atrim=duration={0.2 - 1 / 30:.6f},"
        f"afade=t=out:st={0.19 - 1 / 30:.6f}:d=0.010000,"
        "volume=-6dB,adelay=delays=33.333:all=1[c]"
    )


def test_the_bus_ducks_only_in_speech_the_sfx_sound_in() -> None:
    whoosh = [sfx(1, 1.0, 1.5)]
    assert merged_spans([(2.0, 3.0), (0.5, 1.0), (1.05, 1.2)], 0.1) == [
        (0.5, 1.2),
        (2.0, 3.0),
    ]
    assert duck_filter([], whoosh) == ""
    assert duck_filter([(3.0, 4.0)], whoosh) == ""
    assert duck_filter([(0.2, 0.5), (0.55, 1.1), (3.0, 4.0)], whoosh) == (
        "volume=volume='1-0.498813*min(1,min(clip((t-0.150000)/0.05,0,1),"
        "clip((1.150000-t)/0.05,0,1)))':eval=frame"
    )


def test_the_graph_mixes_every_sfx_into_the_sound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sfx_mix, "sound_seconds", lambda path: 0.5)
    assert audio_graph([], [], {}, "[0:a]", "[out]") == "[0:a]anull[out]"
    one = audio_graph([sfx(2, 1.0, 1.5)], [], {}, "[0:a]", "[out]", rubberband=False)
    assert one.split(";")[1:] == [
        "[sfx2]anull[sfx_bus]",
        "[0:a][sfx_bus]amix=inputs=2:duration=first:normalize=0[out]",
    ]
    assert str(SFX_DIR / "whoosh_swift.flac") in one
    two = audio_graph(
        [sfx(2, 1.0, 1.5), sfx(5, 2.0, 2.5, "7")],
        [(2.1, 2.2)],
        {"7": SOUND},
        "[0:a]",
        "[out]",
        rubberband=False,
    )
    parts = two.split(";")
    assert parts[1].startswith(f"{AMOVIE},volume") and parts[1].endswith("[sfx5]")
    assert parts[2].startswith(
        "[sfx2][sfx5]amix=inputs=2:duration=longest:normalize=0,volume="
    )
    with pytest.raises(ValueError, match="no sound nope"):
        audio_graph([sfx(2, 1.0, 1.5, "nope")], [], {}, "[0:a]", "[out]")


def test_an_asset_names_a_library_file_or_a_bundled_sound() -> None:
    swift = bundled_named("whoosh_swift")
    assert swift is not None and swift == bundled_named("whoosh_swift.flac")
    assert bundled_named("nope") is None
    assert find_sound("whoosh_swift", {}) == SFX_DIR / "whoosh_swift.flac"
    assert find_sound("whoosh_swift", {"whoosh_swift": SOUND}) == SOUND
    assert find_sound("12", {"12": SOUND}) == SOUND
    assert find_sound("12", {}) is None
    assert sound_seconds(SFX_DIR / "whoosh_swift.flac") == pytest.approx(0.5, abs=0.01)


def test_unplayable_sounds_are_named(tmp_path: Path) -> None:
    items = [sfx(1, 0, 1, "whoosh_soft"), sfx(2, 0, 1, "nope"), sfx(3, 0, 1, "4")]
    problems = sound_problems(items, {"4": tmp_path / "gone.flac"})
    assert problems[0].startswith(
        "item 2 (sfx): no sound 'nope' (a library asset id or one of "
    )
    assert "whoosh_swift" in problems[0]
    assert (
        problems[1]
        == f"item 3 (sfx): the sound file {tmp_path / 'gone.flac'} is missing"
    )
    assert undrawn(items, {"4": tmp_path / "gone.flac"}) == problems


def test_library_ids_resolve_to_sound_assets_only(engine: Engine) -> None:
    with Session(engine) as session:
        boom = add_asset(session, "sfx", "/l/boom.wav", "CC0-1.0")
        bed = add_asset(session, "music", "/l/bed.mp3", "CC0-1.0")
        logo = add_asset(session, "logo", "/l/logo.png", "CC0-1.0")
        items = [
            sfx(1, 0, 1, str(boom.id)),
            sfx(2, 0, 1, str(bed.id)),
            sfx(3, 0, 1, str(logo.id)),
            sfx(4, 0, 1, "999"),
            sfx(5, 0, 1, "whoosh_soft"),
        ]
        assert library_sounds(session, items) == {
            str(boom.id): Path("/l/boom.wav"),
            str(bed.id): Path("/l/bed.mp3"),
        }


def test_ffmpeg_has_reads_the_filter_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = tmp_path / "ffmpeg"
    fake.write_text(
        "#!/bin/sh\necho ' .. atempo   A->A  Tempo.'\n"
        "echo ' .. rubberband  A->A  Rb.'\n"
    )
    fake.chmod(0o755)
    monkeypatch.setattr("clipforge.config.settings.ffmpeg_bin", str(fake))
    assert ffmpeg_has("rubberband") and ffmpeg_has("atempo")
    assert not ffmpeg_has("subtitles")
    assert not ffmpeg_has("Tempo.")
