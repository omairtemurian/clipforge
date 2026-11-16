"""The rule-based Director (SPEC-v3 3.5, TASK-219): valid plans for every
preset at every intensity, with and without a music bed, the Skull Moment
sequence, pattern interrupts, determinism and the moves left out."""

import json
from collections import Counter
from pathlib import Path

import pytest
from clipforge.models import EdlItem, ProEditIntensity, ProEditPreset
from clipforge.proedit.audio.drop import IMPACT
from clipforge.proedit.beats import MusicGrid
from clipforge.proedit.budgets import INTENSITIES, budget_problems, effective_budget
from clipforge.proedit.director_music import MusicChoice
from clipforge.proedit.director_rules import RulePlan, _bar_start, rule_plan
from clipforge.proedit.director_skull import HOLD_MAX_S, HOLD_MIN_S
from clipforge.proedit.edl import validate_plan
from clipforge.proedit.preset_defs import Rule, get_preset, load_presets
from clipforge.proedit.signal_models import ProEditSignals

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "proedit_signals_expected.json"
)
SIGNALS = ProEditSignals.model_validate(json.loads(FIXTURE.read_text()))
BPM = 140
BEAT_S = 60 / BPM
BEATS = [round(n * BEAT_S, 4) for n in range(int(30 / BEAT_S))]
MUSIC = MusicChoice(
    "night_drive",
    MusicGrid(duration=30, bpm=BPM, beats=BEATS, downbeats=BEATS[::4]),
    1.0,
)
PRESETS: list[ProEditPreset] = sorted(load_presets())
CHEESE_END = 16.35


def plan_of(
    preset: ProEditPreset, intensity: ProEditIntensity, music: MusicChoice | None = None
) -> RulePlan:
    return rule_plan(SIGNALS, get_preset(preset), preset, intensity, music, plan_id=3)


def at(items: list[EdlItem], kind: str, t: float) -> list[EdlItem]:
    return [i for i in items if i.kind == kind and abs(i.t_start - t) < 1e-6]


@pytest.mark.parametrize("music", [None, MUSIC], ids=["no_bed", "bed"])
@pytest.mark.parametrize("intensity", INTENSITIES)
@pytest.mark.parametrize("preset", PRESETS)
def test_every_preset_and_intensity_gives_a_valid_plan(
    preset: ProEditPreset, intensity: ProEditIntensity, music: MusicChoice | None
) -> None:
    result = plan_of(preset, intensity, music)
    plan = result.plan
    budget = effective_budget(intensity, get_preset(preset).budgets.get(intensity))

    validate_plan(plan, SIGNALS.duration)
    assert budget_problems(plan.items, budget, SIGNALS.duration) == []
    assert (plan.id, plan.clip_id, plan.preset, plan.intensity) == (
        3,
        SIGNALS.clip_id,
        preset,
        intensity,
    )
    assert plan.created_by == "rule_director" and plan.version == 1
    assert get_preset(preset).name in plan.rationale
    assert {i.kind for i in plan.items} <= get_preset(preset).kinds
    assert len({i.id for i in plan.items}) == len(plan.items)
    assert result.interrupt_gaps == []
    assert [i.kind for i in plan.items].count("caption_style") == 1
    assert ("music_bed" in {i.kind for i in plan.items}) == (music is not None)
    assert all(i.source == "auto" and i.reason for i in plan.items)
    on_frames = [
        round(t * SIGNALS.fps, 6) for i in plan.items for t in (i.t_start, i.t_end)
    ]
    assert all(f == round(f) for f in on_frames)


def test_more_intensity_gives_more_moves() -> None:
    for preset in PRESETS:
        counts = [len(plan_of(preset, i).plan.items) for i in INTENSITIES]
        assert counts[0] < counts[-1], preset
        assert counts == sorted(counts), (preset, counts)


def test_the_same_input_gives_the_same_plan() -> None:
    for preset in PRESETS:
        assert plan_of(preset, "pro", MUSIC) == plan_of(preset, "pro", MUSIC)


def test_the_skull_moment_sequence_at_extreme() -> None:
    items = plan_of("skull_moment", "extreme", MUSIC).plan.items
    caught = 491 / 30  # the first frame after the strongest punchline word
    assert caught >= CHEESE_END
    freezes = at(items, "freeze_frame", caught)
    assert len(freezes) == 1
    hold = freezes[0].t_end - caught
    assert HOLD_MIN_S <= hold <= HOLD_MAX_S
    snap_back = caught + hold
    grade = at(items, "grade_change", caught)
    assert [g.params["look"] for g in grade] == ["bw"]
    assert grade[0].t_end == freezes[0].t_end
    overlay = at(items, "overlay", caught)
    assert [(o.params["asset"], o.params["anchor"]) for o in overlay] == [
        ("skull", "face")
    ]
    assert overlay[0].t_end == freezes[0].t_end
    assert len(at(items, "shake", caught)) == 1
    assert [z.params["scale"] for z in at(items, "zoom_punch", caught)] == [1.25]
    assert [s.params["asset"] for s in at(items, "sfx", caught)] == [IMPACT]
    assert [a.params["effect"] for a in at(items, "audio_fx", caught)] == ["bass_boost"]
    silences = [i for i in items if i.kind == "silence_before_drop"]
    assert any(abs(s.t_end - caught) < 1e-6 for s in silences)
    whoosh = at(items, "sfx", snap_back)
    assert [w.params["asset"] for w in whoosh] == ["whoosh_swift"]
    assert "snap back" in whoosh[0].reason
    later = [
        i for i in items if i.kind == "grade_change" and i.t_end > snap_back + 1e-6
    ]
    assert later == []
    risers = [
        i for i in items if i.kind == "sfx" and i.params["asset"] == "riser_swell"
    ]
    assert all(r.t_end <= caught - 0.1 for r in risers)


def test_the_skull_moment_is_placed_whole_at_every_intensity() -> None:
    caught = 491 / 30
    for intensity in INTENSITIES:
        result = plan_of("skull_moment", intensity)
        items = result.plan.items
        kinds = {i.kind for i in items if abs(i.t_start - caught) < 1e-6}
        assert {
            "freeze_frame",
            "grade_change",
            "overlay",
            "zoom_punch",
            "shake",
            "sfx",
            "audio_fx",
        } <= kinds, intensity
        assert len(at(items, "sfx", caught)) == 1, intensity
        left = [lo for lo in result.left_out if "caught moment" in lo.reason]
        assert left == [], intensity


def test_presets_without_a_skull_rule_never_freeze_in_black_and_white() -> None:
    for preset in PRESETS:
        if preset == "skull_moment":
            continue
        items = plan_of(preset, "extreme", MUSIC).plan.items
        assert not [
            i for i in items if i.kind == "overlay" and i.params["asset"] == "skull"
        ]


def test_moves_left_out_say_why() -> None:
    result = plan_of("phonk_edit", "standard", MUSIC)
    assert result.left_out
    assert all(lo.why and lo.reason for lo in result.left_out)


def test_phonk_hits_the_downbeats_and_the_punchline() -> None:
    items = plan_of("phonk_edit", "extreme", MUSIC).plan.items
    kinds = Counter(i.kind for i in items)
    assert kinds["zoom_punch"] >= 5 and kinds["shake"] >= 1 and kinds["flash"] >= 1
    beat_times = {round(b - MUSIC.offset, 4) for b in BEATS}
    punches = [i for i in items if i.kind == "zoom_punch"]
    on_beat = [
        p for p in punches if any(abs(p.t_start - b) <= 1 / 30 for b in beat_times)
    ]
    assert len(on_beat) >= len(punches) // 2
    impacts = [i for i in items if i.kind == "sfx" and i.params["asset"] == IMPACT]
    assert any(abs(i.t_start - 10.6) < 0.05 for i in impacts)


def test_phonk_punches_and_shakes_on_a_beat_snap_back_on_the_next_beat() -> None:
    beat_times = [round(b - MUSIC.offset, 4) for b in BEATS]

    def beat_index(t: float) -> int | None:
        return next(
            (n for n, b in enumerate(beat_times) if abs(t - b) <= 0.5 / 30), None
        )

    for intensity in ("pro", "extreme"):
        items = plan_of("phonk_edit", intensity, MUSIC).plan.items
        moves = [i for i in items if i.kind in ("zoom_punch", "shake")]
        on_beat = [(i, beat_index(i.t_start)) for i in moves]
        on_beat = [(i, n) for i, n in on_beat if n is not None]
        assert len(on_beat) >= 5, intensity
        for move, n in on_beat:
            end = min(beat_times[n + 1], SIGNALS.duration)  # cut at the clip end
            assert abs(move.t_end - end) <= 1 / 30 + 1e-6, move


def test_a_beat_rule_counts_its_phase_from_the_first_downbeat() -> None:
    rule = Rule(signal="beat", moves=["flash"], every=4, phase=2)

    def bed(first_downbeat: int) -> MusicChoice:
        downbeats = BEATS[first_downbeat::4]
        grid = MusicGrid(duration=30, bpm=BPM, beats=BEATS, downbeats=downbeats)
        return MusicChoice("night_drive", grid, 0.0)

    assert _bar_start(rule, bed(0), SIGNALS.duration) == 0
    pickup = bed(1)
    assert _bar_start(rule, pickup, SIGNALS.duration) == 1
    assert _bar_start(rule, MUSIC, SIGNALS.duration) == 1  # 1 s offset
    assert _bar_start(rule, None, SIGNALS.duration) == 0
    downbeat_rule = rule.model_copy(update={"signal": "downbeat"})
    assert _bar_start(downbeat_rule, pickup, SIGNALS.duration) == 0


def test_without_a_bed_phonk_punches_keep_their_length_in_seconds() -> None:
    items = plan_of("phonk_edit", "pro").plan.items
    punches = [i for i in items if i.kind == "zoom_punch"]
    assert punches
    assert all(abs(p.t_end - p.t_start - 0.5) < 1e-6 for p in punches)


def test_cinematic_slows_down_the_punchline_and_has_no_hard_cuts() -> None:
    items = plan_of("cinematic", "standard").plan.items
    slow = [i for i in items if i.kind == "slowmo"]
    assert slow and all(s.t_start >= 10.6 - 1e-6 for s in slow)
    assert not {"zoom_punch", "flash", "glitch", "shake"} & {i.kind for i in items}


def test_no_sfx_covers_a_punchline_word() -> None:
    words = [(p.start, p.end) for p in SIGNALS.punchlines]
    for preset in PRESETS:
        for item in plan_of(preset, "extreme", MUSIC).plan.items:
            if item.kind == "sfx":
                assert all(
                    item.t_end <= w0 + 1e-6 or item.t_start >= w1 - 1e-6
                    for w0, w1 in words
                )


def test_pro_and_extreme_plans_leave_no_interrupt_gap() -> None:
    for preset in PRESETS:
        for intensity in ("pro", "extreme"):
            assert plan_of(preset, intensity).interrupt_gaps == []
