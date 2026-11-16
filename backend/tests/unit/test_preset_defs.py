"""The Pro Edit presets (SPEC-v3 3.4, TASK-219): the six YAML files load,
a bad preset is refused with what is wrong, and the music, key words and
moments the rule-based Director builds on."""

import json
from pathlib import Path
from typing import Any, get_args

import pytest
import yaml
from clipforge.models import ProEditPreset
from clipforge.proedit.beats import MusicGrid
from clipforge.proedit.director_moments import key_words, moments
from clipforge.proedit.director_music import (
    MusicCandidate,
    MusicChoice,
    bundled_candidates,
    pick_music,
)
from clipforge.proedit.preset_defs import (
    PRESETS_DIR,
    MusicSpec,
    PresetDef,
    load_preset,
    load_presets,
)
from clipforge.proedit.signal_models import ProEditSignals

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "proedit_signals_expected.json"
)
SIGNALS = ProEditSignals.model_validate(json.loads(FIXTURE.read_text()))


def raw(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((PRESETS_DIR / f"{name}.yaml").read_text())
    return data


def test_there_is_one_valid_preset_per_id() -> None:
    presets = load_presets()
    assert set(presets) == set(get_args(ProEditPreset))
    assert len({p.name for p in presets.values()}) == 6
    assert all(p.rules and p.description for p in presets.values())
    assert presets["skull_moment"].skull is not None
    assert all(p.skull is None for n, p in presets.items() if n != "skull_moment")
    assert presets["phonk_edit"].music.bpm == (120, 160)
    assert presets["phonk_edit"].beat_lengths == {"zoom_punch": 1, "shake": 1}


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"kinds": ["zoom_punch", "caption_style", "music_bed"]}, "does not allow"),
        ({"skull": None}, "skull is set exactly when"),
        ({"params": {"zoom_punch": {"scale": 3}}}, "params of zoom_punch"),
        ({"overlays": ["no_such_overlay"]}, "overlay set"),
        (
            {"budgets": {"pro": {"effects": {"count": 9, "window_s": 1}}}},
            "never raise it",
        ),
        ({"music": {"moods": ["dark"], "bpm": [160, 120]}}, "low to high"),
        ({"beat_lengths": {"zoom_punch": 0}}, "beat_lengths"),
        ({"rules": [{"on": "punchline", "moves": ["skull_moment"]}]}, "signal"),
    ],
)
def test_a_bad_preset_is_refused_with_the_reason(
    tmp_path: Path, change: dict[str, Any], message: str
) -> None:
    path = tmp_path / "skull_moment.yaml"
    path.write_text(yaml.safe_dump({**raw("skull_moment"), **change}))
    with pytest.raises(ValueError, match=message):
        load_preset(path)


def test_the_preset_folder_needs_every_preset(tmp_path: Path) -> None:
    (tmp_path / "skull_moment.yaml").write_text(yaml.safe_dump(raw("skull_moment")))
    with pytest.raises(ValueError, match="one file per preset"):
        load_presets(tmp_path)


def test_rules_keep_their_order_and_defaults() -> None:
    preset = PresetDef.model_validate(raw("phonk_edit"))
    beat = next(r for r in preset.rules if r.signal == "beat")
    assert (beat.every, beat.phase, beat.cycle, beat.from_intensity) == (
        4,
        2,
        True,
        "standard",
    )
    assert preset.rules[0].signal == "hook"


def test_pick_music_prefers_moods_and_bpm_in_range() -> None:
    spec = MusicSpec(moods=["dark", "phonk"], bpm=(120, 160))
    fast = MusicCandidate("b_fast", ("dark",), 140)
    slow = MusicCandidate("a_slow", ("dark",), 90)
    unknown = MusicCandidate("c_unknown", ("dark", "phonk"))
    assert pick_music(spec, [slow, fast]) == fast
    assert pick_music(spec, [slow, fast, unknown]) == fast
    assert pick_music(spec, [MusicCandidate("calm", ("calm",))]) is None
    tie = pick_music(spec, [unknown, MusicCandidate("a", ("dark", "phonk"))])
    assert tie is not None and tie.asset == "a"
    bundled = pick_music(MusicSpec(moods=["calm"], bpm=(60, 100)), bundled_candidates())
    assert bundled is not None and "calm" in bundled.moods


def test_music_choice_gives_beats_in_clip_seconds() -> None:
    grid = MusicGrid(
        duration=10, bpm=120, beats=[0.5, 1.0, 1.5, 2.0], downbeats=[0.5, 2.5]
    )
    choice = MusicChoice("x", grid, offset=1.0)
    assert choice.beats(0.9) == (0.0, 0.5)
    assert choice.downbeats(5.0) == (1.5,)


def test_key_words_are_the_longest_word_of_each_sentence_outside_punchlines() -> None:
    words = [w.text for w in key_words(SIGNALS)]
    assert len(words) == len(SIGNALS.sentences)
    assert not {"night.", "cheese."} & set(words)
    marked = SIGNALS.model_copy(
        update={
            "words": [
                w.model_copy(update={"emphasis": w.text == "fridges."})
                for w in SIGNALS.words
            ]
        }
    )
    assert [w.text for w in key_words(marked)] == ["fridges."]


def test_moments_of_each_signal() -> None:
    punchlines = moments("punchline", SIGNALS, None)
    assert [m.word.text for m in punchlines if m.word] == ["cheese.", "night."]
    assert [m.t for m in moments("scene_cut", SIGNALS, None)] == [5.5]
    assert moments("hook", SIGNALS, None)[0].t < 2.0
    assert all(m.end > m.t for m in moments("setup", SIGNALS, None))
    assert moments("beat", SIGNALS, None) == []
    peaks = moments("energy_peak", SIGNALS, None)
    assert [(m.t, m.end) for m in peaks] == [(16.9, 17.5)]
