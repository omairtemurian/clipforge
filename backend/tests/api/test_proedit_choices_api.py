"""Tests of GET /proedit/clips/{id}/choices (SPEC-v3 3.8): what the Pro Edit
dialog offers for a clip: the six presets in order with their texts and
music, the music beds by the id ProEditOptions.music takes (bundled loops
by name, uploads by asset id), the style recipes, and the campaign's
heavy-edit rule and intensity cap."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from apihelpers import assert_error
from campaign_api import add, in_campaign
from clipforge.autopilot.rows import AutopilotSettingsRow
from clipforge.ffmpeg import run_ffmpeg
from clipforge.pipeline.music import BUNDLED_TRACKS
from clipforge.proedit.rows import StyleRecipeRow
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

API = "/api/proedit"
PRESETS = [
    "clean_pro",
    "dark_edit",
    "phonk_edit",
    "cinematic",
    "skull_moment",
    "glitch",
]


def choices(client: TestClient, clip_id: int) -> dict[str, Any]:
    response = client.get(f"{API}/clips/{clip_id}/choices")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_a_clip_without_a_campaign_gets_every_preset_and_bundled_loop(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "rendered", 80, "Bit")

    body = choices(client, clip_id)

    assert [p["id"] for p in body["presets"]] == PRESETS
    phonk = body["presets"][2]
    assert phonk["name"] == "Phonk Edit"
    assert phonk["description"].startswith("Dark look cut to a heavy beat")
    assert (phonk["bpm_min"], phonk["bpm_max"]) == (120, 160)
    assert "phonk" in phonk["music_moods"]
    loops = [Path(track.file).stem for track in BUNDLED_TRACKS]
    assert [m["id"] for m in body["music"]] == loops
    assert body["music"][0] == {
        "id": "bright_steps",
        "title": "Bright Steps",
        "tags": ["upbeat", "happy", "pop"],
        "bundled": True,
    }
    assert body["recipes"] == []
    assert body["campaign_id"] is None and body["allow_heavy_edits"] is None
    assert body["max_intensity"] == "extreme"


def test_uploads_are_picked_by_asset_id_and_recipes_are_listed(
    client: TestClient, api_engine: Engine, tmp_path: Path
) -> None:
    song = tmp_path / "song.wav"
    run_ffmpeg(["-f", "lavfi", "-i", "sine=frequency=330:duration=1", song])
    upload = client.post(
        "/api/library",
        files={"file": ("My Song.wav", song.read_bytes())},
        data={"kind": "music", "tags": ["Dark"]},
    )
    assert upload.status_code == 201, upload.text
    with Session(api_engine) as session:
        session.add(
            StyleRecipeRow(
                name="Night phonk",
                description="Fast cuts",
                features={"cuts_per_s": {"median": 0.8}},
                reference_count=2,
                created_at=datetime(2026, 11, 7, tzinfo=UTC),
            )
        )
        session.commit()
    clip_id = add_clip(api_engine, add_project(api_engine), "rendered", 80, "Bit")

    body = choices(client, clip_id)

    own = body["music"][-1]
    assert own == {
        "id": str(upload.json()["asset"]["id"]),
        "title": "My Song.wav",
        "tags": ["dark"],
        "bundled": False,
    }
    [recipe] = body["recipes"]
    assert (recipe["name"], recipe["reference_count"]) == ("Night phonk", 2)
    started = client.get(f"{API}/clips/{clip_id}/estimate", params={"music": own["id"]})
    assert started.status_code != 422, "the dialog's music id must be a valid option"


def test_the_campaign_rule_and_its_autopilot_cap_come_with_the_choices(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client, name="Pizza Clips", allow_heavy_edits="false")
    clip_id = add_clip(
        api_engine, in_campaign(api_engine, campaign["id"]), "rendered", 80, "Bit"
    )

    unset = choices(client, clip_id)
    with Session(api_engine) as session:
        session.add(
            AutopilotSettingsRow(
                campaign_id=campaign["id"], proedit_max_intensity="pro"
            )
        )
        session.commit()
    capped = choices(client, clip_id)

    assert (unset["campaign_id"], unset["campaign_name"]) == (
        campaign["id"],
        "Pizza Clips",
    )
    assert unset["allow_heavy_edits"] == "false"
    assert unset["max_intensity"] == "extreme"
    assert capped["max_intensity"] == "pro"


def test_the_choices_of_a_missing_clip_are_404(client: TestClient) -> None:
    assert_error(client.get(f"{API}/clips/999/choices"), 404, "not_found")
