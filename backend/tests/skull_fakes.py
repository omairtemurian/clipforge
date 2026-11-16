"""Shared inputs of the Skull Moment composite tests (TASK-237): the
fixture clip's signals and beat grid, Skull Moment items and the check that
a plan holds the whole Skull Moment sequence at a time."""

import json
from pathlib import Path

from clipforge.models import EdlItem, ProEditIntensity
from clipforge.proedit.audio.drop import IMPACT
from clipforge.proedit.beats import MusicGrid
from clipforge.proedit.director_catalog import asset_catalog
from clipforge.proedit.director_music import MusicChoice
from clipforge.proedit.director_prompt import DirectorRequest
from clipforge.proedit.preset_defs import get_preset
from clipforge.proedit.signal_models import ProEditSignals

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RECORDED_SKULL = FIXTURES / "proedit_director" / "recorded_skull_standard.json"
SIGNALS = ProEditSignals.model_validate(
    json.loads((FIXTURES / "proedit_signals_expected.json").read_text())
)
BEATS = [round(n * 60 / 140, 4) for n in range(70)]
MUSIC = MusicChoice(
    "night_drive",
    MusicGrid(duration=30, bpm=140, beats=BEATS, downbeats=BEATS[::4]),
    1.0,
)
FRAME = 1 / 30
CAUGHT = 491 / 30  # the first frame after the punchline word "cheese."
SKULL_KINDS = {"freeze_frame", "grade_change", "overlay", "shake", "zoom_punch"}


def item(
    id: int, kind: str, t: float, end: float, source: str = "auto", **params: object
) -> EdlItem:
    """An item of kind from t to end with params."""
    return EdlItem.model_validate(
        {
            "id": id,
            "kind": kind,
            "t_start": t,
            "t_end": end,
            "params": params,
            "reason": f"{kind} at {t:g}",
            "source": source,
        }
    )


def skull(first_id: int, at: float, hold: float = 1.5) -> list[EdlItem]:
    """The items of a Skull Moment at at, numbered from first_id."""
    end = at + hold
    return [
        item(first_id, "freeze_frame", at, end),
        item(first_id + 1, "grade_change", at, end, look="bw"),
        item(first_id + 2, "overlay", at, end, asset="skull", anchor="face"),
        item(first_id + 3, "zoom_punch", at, end, scale=1.25),
        item(first_id + 4, "shake", at, at + 0.5),
        item(first_id + 5, "sfx", at, at + 1.2, asset=IMPACT),
        item(first_id + 6, "audio_fx", at, at + 0.6, effect="bass_boost"),
        item(first_id + 7, "sfx", end, end + 0.3, asset="whoosh_swift"),
    ]


def skull_request(intensity: ProEditIntensity) -> DirectorRequest:
    """The LLM Director's request for a Skull Moment edit of the fixture."""
    return DirectorRequest(
        signals=SIGNALS,
        preset=get_preset("skull_moment"),
        preset_id="skull_moment",
        intensity=intensity,
        music=MUSIC,
        catalog=tuple(asset_catalog()),
        plan_id=2,
    )


def assert_whole_skull(items: list[EdlItem], at: float) -> None:
    """Assert items hold the whole Skull Moment sequence on the frame at:
    freeze, black and white (or dark) grade, skull, punch-in, shake and
    impact, and a whoosh when the freeze ends."""
    found = [
        i
        for i in items
        if abs(i.t_start - at) <= FRAME / 2 and i.t_end - i.t_start < 10
    ]
    kinds = {i.kind for i in found}
    assert SKULL_KINDS <= kinds, sorted(kinds)
    grades = [i.params["look"] for i in found if i.kind == "grade_change"]
    assert grades and set(grades) <= {"bw", "dark"}
    assert [i.params["asset"] for i in found if i.kind == "overlay"] == ["skull"]
    assert IMPACT in [i.params["asset"] for i in found if i.kind == "sfx"]
    freeze = next(i for i in found if i.kind == "freeze_frame")
    snap_back = [
        i
        for i in items
        if i.kind == "sfx" and abs(i.t_start - freeze.t_end) <= FRAME / 2
    ]
    assert snap_back, "no whoosh on the snap back to color"
