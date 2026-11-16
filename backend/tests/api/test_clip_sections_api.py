"""Tests of the section op endpoints (SPEC-v2 3.5, api/clip_sections):
trim/extend, add, split, delete and rearrange a clip's sections through the
API; the video track, cut ranges and scenes follow; each op is a version;
errors are 404, 409 and 422."""

from apihelpers import assert_error
from clipforge.models import ClipStatus
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine

# The seeded clip plays 10-12.5 s of a 60 s source.
SECTIONS = "/api/clips/{}/sections"


def new_clip(
    engine: Engine, status: ClipStatus = "candidate", **changes: object
) -> int:
    """Add a clip (seed.add_clip) with status and changes; return its id."""
    return add_clip(engine, add_project(engine), status, 80, **changes)


def test_add_split_rearrange_and_delete_sections(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = new_clip(api_engine)
    url = SECTIONS.format(clip_id)

    added = client.post(url, json={"start": 30.0, "end": 32.0, "index": 0})
    split = client.post(f"{url}/split", json={"at": 11.0})
    order = client.post(f"{url}/reorder", json={"order": [2, 0, 1]})
    deleted = client.delete(f"{url}/0")

    assert added.status_code == 200
    assert added.json()["segments"] == [[30.0, 32.0], [10.0, 12.5]]
    assert split.json()["segments"] == [[30.0, 32.0], [10.0, 11.0], [11.0, 12.5]]
    assert order.json()["segments"] == [[11.0, 12.5], [30.0, 32.0], [10.0, 11.0]]
    final = deleted.json()
    assert final["segments"] == [[30.0, 32.0], [10.0, 11.0]]
    assert (final["start"], final["end"]) == (10.0, 32.0)
    assert [(i["id"], i["start"], i["end"]) for i in final["tracks"]["video"]] == [
        ("video-0", 30.0, 32.0),
        ("video-1", 10.0, 11.0),
    ]
    history = client.get(f"/api/clips/{clip_id}/versions").json()
    assert history["current"] == 5


def test_trim_and_extend_clamp_to_the_source(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = new_clip(api_engine)
    url = SECTIONS.format(clip_id)

    trimmed = client.put(f"{url}/0", json={"start": 10.5, "end": 12.0})
    extended = client.put(f"{url}/0", json={"start": 0.0, "end": 99.0})

    assert trimmed.json()["segments"] == [[10.5, 12.0]]
    assert extended.json()["segments"] == [[0.0, 60.0]]


def test_cuts_and_scenes_follow_the_sections(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = new_clip(api_engine, cut_ranges=[(10.5, 11.5), (12.0, 12.2)])
    url = SECTIONS.format(clip_id)

    client.post(f"{url}/split", json={"at": 11.0})
    after = client.delete(f"{url}/1").json()

    assert after["segments"] == [[10.0, 11.0]]
    assert after["cut_ranges"] == [[10.5, 11.0]]


def test_section_errors(client: TestClient, api_engine: Engine) -> None:
    clip_id = new_clip(api_engine)
    rendering = new_clip(api_engine, status="rendering")
    url = SECTIONS.format(clip_id)

    assert_error(client.delete(f"{url}/3"), 404, "not_found")
    assert_error(client.put(f"{url}/1", json={"start": 1, "end": 2}), 404, "not_found")
    assert_error(client.delete(f"{url}/0"), 422, "validation_error")
    overlap = client.post(url, json={"start": 12.0, "end": 14.0})
    assert "overlaps section 0" in assert_error(overlap, 422, "validation_error")
    split = client.post(f"{url}/split", json={"at": 20.0})
    assert_error(split, 422, "validation_error")
    order = client.post(f"{url}/reorder", json={"order": [1]})
    assert_error(order, 422, "validation_error")
    backwards = client.put(f"{url}/0", json={"start": 12.0, "end": 11.0})
    assert_error(backwards, 422, "validation_error")
    assert_error(client.delete(f"{SECTIONS.format(999)}/0"), 404, "not_found")
    busy = client.post(SECTIONS.format(rendering), json={"start": 1, "end": 2})
    assert_error(busy, 409, "conflict")
    assert client.get(f"/api/clips/{clip_id}").json()["segments"] == [[10.0, 12.5]]


def test_a_cut_that_would_leave_nothing_is_refused(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = new_clip(api_engine, cut_ranges=[(11.0, 12.5)])

    response = client.put(
        f"{SECTIONS.format(clip_id)}/0", json={"start": 11.0, "end": 12.5}
    )

    message = assert_error(response, 422, "validation_error")
    assert "leave nothing" in message
