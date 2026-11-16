"""Tests of a clip's transitions through the API (SPEC-v2 3.5): PATCH
/api/clips/{id} saves them (auto on jump cuts, one per section cut), they
are a version of the clip that undo takes back, invalid ones are 422, and
the preview key changes with them."""

import pytest
from apihelpers import assert_error
from clipforge.db import ClipRow
from clipforge.models import ClipTransitions, FaceBox, Transition
from clipforge.pipeline.faces import sample_times
from clipforge.pipeline.reframe import ClipSpan, plan_crop
from clipforge.preview import preview_key
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

TRANSITIONS = {
    "auto": {"kind": "zoom_punch", "duration": 0.25},
    "sections": [None, {"kind": "slide"}],
}


def test_patch_saves_the_transitions_as_a_version(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    assert client.get(f"/api/clips/{clip_id}").json()["transitions"] == {
        "auto": None,
        "sections": [],
    }

    response = client.patch(f"/api/clips/{clip_id}", json={"transitions": TRANSITIONS})

    assert response.status_code == 200
    assert response.json()["transitions"]["sections"][1] == {
        "kind": "slide",
        "duration": 0.3,
    }
    with Session(api_engine) as session:
        saved = session.get_one(ClipRow, clip_id).to_model().transitions
    assert saved == ClipTransitions(
        auto=Transition(kind="zoom_punch", duration=0.25),
        sections=[None, Transition(kind="slide")],
    )
    history = client.get(f"/api/clips/{clip_id}/versions").json()
    assert history["versions"][-1]["fields"] == ["transitions"]
    undone = client.post(f"/api/clips/{clip_id}/undo").json()
    assert undone["transitions"] == {"auto": None, "sections": []}


@pytest.mark.parametrize(
    "transitions",
    [
        {"auto": {"kind": "spin"}},
        {"auto": {"kind": "crossfade", "duration": 0.05}},
        {"auto": {"kind": "crossfade", "duration": 1.5}},
        {"sections": [{"kind": "whip", "speed": 2}]},
    ],
)
def test_invalid_transitions_are_refused(
    client: TestClient, api_engine: Engine, transitions: dict[str, object]
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)

    response = client.patch(f"/api/clips/{clip_id}", json={"transitions": transitions})

    assert_error(response, 422, "validation_error")


def test_the_preview_key_changes_with_the_transitions(api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80)
    with Session(api_engine) as session:
        clip = session.get_one(ClipRow, clip_id).to_model()
    faces: list[list[FaceBox]] = [[] for _ in sample_times(10.0, 12.5)]
    plan = plan_crop(ClipSpan(clip_id, 10.0, 12.5), "9:16", (1280, 720), faces, [])
    faded = clip.model_copy(
        update={"transitions": ClipTransitions(auto=Transition(kind="crossfade"))}
    )

    assert preview_key(faded, plan) != preview_key(clip, plan)
