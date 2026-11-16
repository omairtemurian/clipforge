"""Unit tests of the Pro Edit music beds, drop moves and audio effects
(SPEC-v3 3.3, TASK-215): where each bed's music starts, how a drop cuts the
beds and adds its moves, the sweep's cutoffs and the filter strings."""

from pathlib import Path

import pytest
from clipforge.models import EdlItem
from clipforge.pipeline.music import MUSIC_DIR
from clipforge.proedit.audio.drop import (
    BASS_DROP_AMOUNT,
    IMPACT,
    RISER,
    drop_moves,
    split_beds,
)
from clipforge.proedit.audio.envelope import gate_filter, level_expr
from clipforge.proedit.audio.fx import (
    SWEEP_FLOOR_HZ,
    SWEEP_OPEN_HZ,
    fx_graph,
    stutter_filters,
    sweep_filters,
    sweep_hz,
    wet_filters,
)
from clipforge.proedit.audio.mix import DIALOGUE_FILTER, sound_graph
from clipforge.proedit.audio.music_bed import (
    bed_filter,
    bed_offsets,
    music_graph,
    silence_spans,
)
from clipforge.proedit.audio.sounds import find_sound, sound_problems
from clipforge.proedit.edl import AudioFxItem, MusicBedItem, parse_item
from clipforge.proedit.snap import PlanTiming
from edl_fakes import item, plan

FPS = 30
TIMING = PlanTiming(FPS, 10.0)
LOOP = Path("/m/loop.flac")
LIBRARY = {"7": LOOP}


def bed(
    id: int, start: float, end: float, asset: str = "7", **params: object
) -> MusicBedItem:
    parsed = parse_item(
        item(id, "music_bed", start, end, params={"asset": asset, **params})
    )
    assert isinstance(parsed, MusicBedItem)
    return parsed


def fx(id: int, start: float, end: float, effect: str, amount: float) -> AudioFxItem:
    params = {"effect": effect, "amount": amount}
    parsed = parse_item(item(id, "audio_fx", start, end, params=params))
    assert isinstance(parsed, AudioFxItem)
    return parsed


def frames(items: list[EdlItem]) -> list[tuple[str, int, int]]:
    return [(i.kind, round(i.t_start * FPS), round(i.t_end * FPS)) for i in items]


def test_a_bed_continues_the_music_of_the_bed_before_it() -> None:
    beds = [
        bed(1, 0.0, 2.0),
        bed(2, 2.5, 4.0),
        bed(3, 1.0, 3.0, asset="night_drive"),
        bed(4, 5.0, 6.0, offset=0.5),
        bed(5, 7.0, 8.0),
    ]
    ordered = sorted(beds, key=lambda b: b.t_start)
    assert bed_offsets(ordered) == {1: 0.0, 3: 0.0, 2: 2.5, 4: 0.5, 5: 2.5}


def test_split_beds_cuts_a_bed_around_a_span_and_keeps_its_music() -> None:
    items = [
        item(1, "music_bed", 0.0, 5.0, params={"asset": "7"}),
        item(2, "zoom_punch", 1.0, 2.0, params={"center": "frame"}),
        item(3, "music_bed", 6.0, 8.0, params={"asset": "7"}),
    ]
    cut = split_beds(plan(items, "standard"), 2.0, 2.2)
    assert [(i.id, i.t_start, i.t_end) for i in cut] == [
        (1, 0.0, 2.0),
        (4, 2.2, 5.0),
        (2, 1.0, 2.0),
        (3, 6.0, 8.0),
    ]
    assert cut[1].params == {"asset": "7", "offset": 2.2}


def test_drop_moves_add_the_silence_riser_impact_and_bass_drop() -> None:
    items = [item(1, "music_bed", 0.0, 8.0, params={"asset": "7"})]
    moves = drop_moves(plan(items, "standard"), 3.0, TIMING)
    assert moves.notes == []
    assert frames(moves.plan.items) == [
        ("music_bed", 0, 84),
        ("sfx", 36, 84),
        ("silence_before_drop", 84, 90),
        ("music_bed", 90, 240),
        ("sfx", 90, 126),
        ("audio_fx", 90, 108),
    ]
    by_kind = {(i.kind, i.params.get("asset")): i for i in moves.plan.items}
    assert by_kind[("sfx", RISER)].params["fit"] == "stretch"
    assert ("sfx", IMPACT) in by_kind
    assert by_kind[("audio_fx", None)].params == {
        "effect": "bass_boost",
        "amount": BASS_DROP_AMOUNT,
    }
    beds = [i.params for i in moves.plan.items if i.kind == "music_bed"]
    assert beds == [{"asset": "7"}, {"asset": "7", "offset": 3.0}]


def test_drop_moves_without_a_riser_add_only_the_silence_and_the_hit() -> None:
    items = [item(1, "music_bed", 0.0, 8.0, params={"asset": "7"})]
    moves = drop_moves(plan(items, "standard"), 3.0, TIMING, riser=False)
    assert moves.notes == []
    assert [i.params.get("asset") for i in moves.plan.items if i.kind == "sfx"] == [
        IMPACT
    ]
    assert [i.kind for i in moves.plan.items].count("silence_before_drop") == 1


def test_drop_moves_leave_out_what_does_not_fit_with_a_note() -> None:
    clash = item(1, "audio_fx", 3.2, 3.4, params={"effect": "stutter"})
    moves = drop_moves(plan([clash], "standard"), 0.3, TIMING, silence_s=0.1)
    assert [(n.kind, n.action) for n in moves.notes] == [("sfx", "dropped")]
    assert "no room for a riser" in moves.notes[0].reason
    moves = drop_moves(plan([clash], "standard"), 3.0, TIMING)
    assert [(n.kind, n.action) for n in moves.notes] == [("audio_fx", "dropped")]
    assert [i.kind for i in moves.plan.items].count("audio_fx") == 1


@pytest.mark.parametrize(
    ("drop", "silence", "message"),
    [
        (3.0, 0.5, "0.1 to 0.3 s"),
        (0.1, 0.2, "no room"),
        (10.0, 0.2, "no room"),
    ],
)
def test_drop_moves_refuse_a_silence_that_cannot_be(
    drop: float, silence: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        drop_moves(plan([], "standard"), drop, TIMING, silence_s=silence)


def test_the_sweep_opens_exponentially_to_the_full_band() -> None:
    full = fx(1, 1.0, 2.0, "lowpass_sweep", 1.0)
    assert sweep_hz(full, 0.0) == pytest.approx(SWEEP_FLOOR_HZ)
    assert sweep_hz(full, 1.5) == pytest.approx(2000.0)
    assert sweep_hz(full, 9.0) == pytest.approx(SWEEP_OPEN_HZ)
    half = fx(1, 1.0, 2.0, "lowpass_sweep", 0.5)
    assert sweep_hz(half, 1.0) == pytest.approx(2000.0)
    commands, lowpass = sweep_filters(fx(3, 1.0, 1.04, "lowpass_sweep", 1.0))
    assert commands == (
        "asendcmd=c='1.000000 lowpass@sweep3 frequency 200.0;"
        "1.020000 lowpass@sweep3 frequency 2000.0;"
        "1.040000 lowpass@sweep3 frequency 20000.0'"
    )
    assert lowpass == "lowpass@sweep3=f=200.0"


def test_stutter_repeats_the_windows_first_slice() -> None:
    # amount 0.5: 2 + 3 = 5 slices of 0.1 s over a 0.5 s window
    assert stutter_filters(fx(1, 2.0, 2.5, "stutter", 0.5)) == [
        "atrim=start=2.000000:duration=0.100000",
        "asetpts=PTS-STARTPTS",
        "afade=t=in:st=0:d=0.003000",
        "afade=t=out:st=0.097000:d=0.003000",
        "aloop=loop=-1:size=4800",
        "atrim=duration=0.500000",
        "asetpts=N/SR/TB",
        "adelay=delays=2000.000:all=1",
        "asetpts=N/SR/TB",
    ]


def test_each_effect_is_gated_to_its_window() -> None:
    gate = gate_filter([(1.0, 2.0)], 0.005, inside=True)
    assert wet_filters(fx(1, 1.0, 2.0, "bass_boost", 0.5)) == [
        "bass=g=6.000:f=100",
        gate,
    ]
    reverb = wet_filters(fx(1, 1.0, 2.0, "reverb_tail", 1.0))
    assert reverb[0] == gate
    assert reverb[1].startswith("aecho=in_gain=1:out_gain=1:delays=43|79|")
    assert ":decays=0.6000|0.4500|" in reverb[1]
    assert gate.startswith("aformat=channel_layouts=stereo,aeval=")
    assert gate.endswith(":c=stereo,aformat=channel_layouts=stereo")
    assert level_expr([(1.005, 1.995)], 0.005) in gate


def test_fx_graph_splits_dry_and_wet_per_effect_in_time_order() -> None:
    items = [fx(2, 3.0, 3.5, "stutter", 0.5), fx(1, 1.0, 2.0, "bass_boost", 0.5)]
    graph = fx_graph(items, "[src]", "[out]").split(";")
    assert graph[0] == "[src]aresample=48000[fx_in0]"
    assert graph[1] == "[fx_in0]asplit=2[fx1_dry][fx1_src]"
    assert graph[4].endswith("amix=inputs=2:duration=first:normalize=0[fx_in1]")
    assert graph[5] == "[fx_in1]asplit=2[fx2_dry][fx2_src]"
    assert graph[-1] == "[fx_in2]anull[out]"
    assert fx_graph([], "[src]", "[out]") == "[src]anull[out]"


def test_a_bed_loops_from_its_offset_and_ducks_under_speech() -> None:
    chain = bed_filter(bed(1, 2.0, 4.0, gain_db=-20), LOOP, 1.5, [(2.5, 3.0)], "[b]")
    parts = chain.split(",")
    assert parts[:4] == [
        "amovie=filename=/m/loop.flac:loop=0",
        "aresample=48000",
        "asetpts=N/SR/TB",
        "atrim=start=1.500000:duration=2.000000",
    ]
    assert "volume=-20dB" in parts
    assert "adelay=delays=2000.000:all=1" in parts
    assert "volume=volume='1-0.748811*" in chain
    assert chain.endswith("[b]")
    quiet = bed_filter(bed(1, 2.0, 4.0, duck=False), LOOP, 0.0, [(2.5, 3.0)], "[b]")
    assert "eval=frame" not in quiet


def test_music_graph_mixes_the_beds_into_the_source() -> None:
    graph = music_graph([bed(2, 3.0, 4.0), bed(1, 0.0, 2.0)], [], LIBRARY, "[a]", "[o]")
    parts = graph.split(";")
    assert "atrim=start=0.000000:duration=2.000000" in parts[0]
    assert "atrim=start=3.000000:duration=1.000000" in parts[1]
    assert (
        parts[2] == "[bed1][bed2]amix=inputs=2:duration=longest:normalize=0[music_bus]"
    )
    assert parts[3] == "[a][music_bus]amix=inputs=2:duration=first:normalize=0[o]"
    with pytest.raises(ValueError, match="no sound nope"):
        music_graph([bed(1, 0.0, 2.0, asset="nope")], [], {}, "[a]", "[o]")


def test_sound_graph_chains_only_the_stages_with_items() -> None:
    assert sound_graph([], [], {}, "[a]", "[o]") == "[a]anull[o]"
    only_fx = [fx(1, 1.0, 2.0, "bass_boost", 0.5)]
    assert sound_graph(only_fx, [], {}, "[a]", "[o]") == fx_graph(only_fx, "[a]", "[o]")
    both = sound_graph([bed(1, 0.0, 2.0), *only_fx], [], LIBRARY, "[a]", "[o]")
    assert "normalize=0[pro_sound1]" in both
    assert "[pro_sound1]aresample=48000[fx_in0]" in both


def test_sound_graph_puts_the_dialogue_chain_first_and_the_master_last() -> None:
    assert sound_graph([], [], {}, "[a]", "[o]", dialogue=True, master="loudnorm") == (
        f"[a]{DIALOGUE_FILTER}[pro_sound1];[pro_sound1]loudnorm[o]"
    )
    mixed = sound_graph(
        [bed(1, 0.0, 2.0)], [], LIBRARY, "[a]", "[o]", dialogue=True, master="loudnorm"
    )
    assert mixed.startswith(f"[a]{DIALOGUE_FILTER}[pro_sound1];")
    assert mixed.endswith("[pro_sound2]loudnorm[o]")
    assert sound_graph([], [], {}, "[a]", "[o]", dialogue=True) == (
        f"[a]{DIALOGUE_FILTER}[o]"
    )


def test_silences_and_bundled_tracks_are_found() -> None:
    silence = parse_item(item(3, "silence_before_drop", 2.8, 3.0, params={}))
    assert silence_spans([silence, bed(1, 0.0, 2.8)]) == [(2.8, 3.0)]
    assert find_sound("night_drive", {}) == MUSIC_DIR / "night_drive.flac"
    assert find_sound("slow_tide.flac", {}) == MUSIC_DIR / "slow_tide.flac"
    problems = sound_problems([bed(1, 0.0, 2.0, asset="nope")], {})
    assert len(problems) == 1
    assert "music_bed" in problems[0]
    assert "night_drive" in problems[0]
