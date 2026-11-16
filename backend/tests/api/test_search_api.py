"""Tests of the library search endpoints (/api/search): hits with the
project and the exact second, and a clip made from a moment of a hit."""

from pathlib import Path
from typing import Any

from apihelpers import assert_error
from fastapi.testclient import TestClient
from seed import add_project, add_work
from sqlalchemy import Engine


def library(client: TestClient, engine: Engine, sample_mp4: Path) -> int:
    project = add_project(engine)
    add_work(engine, project, sample_mp4)
    return project


def moment(client: TestClient, **body: Any) -> Any:
    return client.post("/api/search/clips", json=body)


def test_a_search_answers_the_project_and_the_second_of_each_hit(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project = library(client, api_engine, sample_mp4)

    response = client.get("/api/search", params={"q": "Cheese"})

    assert response.status_code == 200
    [hit] = response.json()
    assert hit["project_id"] == project
    assert hit["project_title"] == "talk"
    assert hit["segment_id"] == 7
    assert 27.65 < hit["start"] < 32.85
    assert (hit["segment_start"], hit["end"]) == (27.65, 32.85)
    marked = hit["highlights"][0]
    assert hit["text"][marked["start"] : marked["end"]] == "cheese"


def test_a_search_can_be_limited_to_a_project_and_in_size(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    first = library(client, api_engine, sample_mp4)
    second = library(client, api_engine, sample_mp4)

    both = client.get("/api/search", params={"q": "yoga"}).json()
    one = client.get("/api/search", params={"q": "yoga", "project_id": second}).json()
    few = client.get("/api/search", params={"q": "the", "limit": 2}).json()

    assert sorted(h["project_id"] for h in both) == [first, second]
    assert [h["project_id"] for h in one] == [second]
    assert len(few) == 2
    assert client.get("/api/search", params={"q": "zzzz"}).json() == []


def test_a_search_needs_words(client: TestClient) -> None:
    assert_error(
        client.get("/api/search", params={"q": '" - "'}), 422, "validation_error"
    )
    assert_error(client.get("/api/search", params={"q": ""}), 422, "validation_error")
    assert_error(client.get("/api/search"), 422, "validation_error")
    assert_error(
        client.get("/api/search", params={"q": "a", "limit": 0}),
        422,
        "validation_error",
    )


def test_a_clip_is_made_from_the_moment_of_a_hit(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project = library(client, api_engine, sample_mp4)
    [hit] = client.get("/api/search", params={"q": "cheese"}).json()

    response = moment(client, project_id=project, at=hit["start"], length=10)

    assert response.status_code == 201, response.text
    clip = response.json()
    assert clip["project_id"] == project
    assert (clip["start"], clip["end"]) == (27.65, 32.85)
    assert clip["segments"] == [[27.65, 32.85]]
    assert clip["status"] == "candidate"
    assert clip["title"].startswith("Last night the notification")
    assert clip["output_path"] is None
    assert clip["result_set"] == 1
    listed = client.get(f"/api/projects/{project}/clips").json()
    assert [c["id"] for c in listed] == [clip["id"]]


def test_the_clip_takes_the_sentences_that_fit_the_length(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project = library(client, api_engine, sample_mp4)

    long = moment(client, project_id=project, at=29.0).json()
    short = moment(client, project_id=project, at=29.0, length=5).json()
    in_pause = moment(client, project_id=project, at=33.0, length=10).json()
    last = moment(client, project_id=project, at=59.0).json()

    assert (long["start"], long["end"]) == (27.65, 56.52)
    assert (short["start"], short["end"]) == (27.65, 32.65)
    assert (in_pause["start"], in_pause["end"]) == (35.8, 41.35)
    assert (last["start"], last["end"]) == (58.45, 59.5)
    assert len({long["id"], short["id"], in_pause["id"], last["id"]}) == 4


def test_no_clip_is_made_where_nothing_is_said_or_the_project_is_wrong(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project = library(client, api_engine, sample_mp4)
    bare = add_project(api_engine)

    assert_error(moment(client, project_id=project, at=59.9), 422, "validation_error")
    assert_error(moment(client, project_id=999, at=1), 404, "not_found")
    assert_error(moment(client, project_id=bare, at=1), 409, "conflict")
    assert_error(moment(client, project_id=project, at=-1), 422, "validation_error")
    assert_error(
        moment(client, project_id=project, at=1, length=1), 422, "validation_error"
    )
    assert client.get(f"/api/projects/{project}/clips").json() == []


def test_a_moment_goes_from_search_to_clip_to_collection(
    client: TestClient, api_engine: Engine, sample_mp4: Path
) -> None:
    project = library(client, api_engine, sample_mp4)
    [hit] = client.get("/api/search", params={"q": "smart fridges"}).json()
    clip = moment(client, project_id=project, at=hit["start"], length=10).json()
    made = client.post("/api/collections", json={"name": "Funny"}).json()

    added = client.post(
        f"/api/collections/{made['id']}/items", json={"clip_ids": [clip["id"]]}
    )

    assert added.status_code == 200
    assert [i["clip_id"] for i in added.json()["items"]] == [clip["id"]]
