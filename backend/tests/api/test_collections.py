"""Tests of the collection endpoints (/api/collections): create, rename,
list, delete, add clips from anywhere (in order, once), remove them, and the
zip with the rendered clips and a manifest."""

import io
import json
import zipfile
from typing import Any

from apihelpers import assert_error
from clipforge.models import CollectionDetail, CollectionManifest
from clipforge.pipeline.render import clip_output
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine


def make(client: TestClient, name: str = "Best of", **body: Any) -> dict[str, Any]:
    response = client.post("/api/collections", json={"name": name, **body})
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()
    return created


def rendered(engine: Engine, project_id: int, title: str, overall: int = 80) -> int:
    """Add a rendered clip whose video, subtitles and metadata files exist."""
    clip_id = add_clip(engine, project_id, "rendered", overall, title)
    video = clip_output(project_id, clip_id)
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_bytes(b"video of " + title.encode())
    video.with_suffix(".srt").write_text("1\n")
    video.with_suffix(".json").write_text("{}")
    return clip_id


def ids(detail: dict[str, Any]) -> list[int]:
    return [item["clip_id"] for item in detail["items"]]


def test_a_collection_starts_empty_and_can_be_renamed(client: TestClient) -> None:
    created = make(client, "  Best of  ", description="My picks")

    assert created["name"] == "Best of"
    assert (created["clip_count"], created["items"]) == (0, [])
    assert created["created_at"].endswith("Z")
    patched = client.patch(f"/api/collections/{created['id']}", json={"name": "Top"})
    assert patched.status_code == 200
    assert (patched.json()["name"], patched.json()["description"]) == (
        "Top",
        "My picks",
    )
    assert patched.json()["updated_at"] >= created["updated_at"]
    CollectionDetail.model_validate(
        client.get(f"/api/collections/{created['id']}").json()
    )


def test_the_list_is_newest_first_with_clip_counts(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 70)
    older, newer = make(client, "Old"), make(client, "New")
    client.post(f"/api/collections/{older['id']}/items", json={"clip_ids": [clip_id]})

    listed = client.get("/api/collections").json()

    assert [(c["name"], c["clip_count"]) for c in listed] == [("New", 0), ("Old", 1)]
    assert "items" not in listed[0]
    assert listed[0]["id"] == newer["id"]


def test_clips_of_any_project_are_added_in_order_and_once(
    client: TestClient, api_engine: Engine
) -> None:
    first_project, second_project = add_project(api_engine), add_project(api_engine)
    a = add_clip(api_engine, first_project, "candidate", 70, "A")
    b = add_clip(api_engine, second_project, "rendered", 90, "B")
    c = add_clip(api_engine, first_project, "candidate", 60, "C")
    collection = make(client)
    url = f"/api/collections/{collection['id']}/items"

    assert client.post(url, json={"clip_ids": [b, a, b]}).status_code == 200
    detail = client.post(url, json={"clip_ids": [c, a]}).json()

    assert ids(detail) == [b, a, c]
    assert [item["position"] for item in detail["items"]] == [0, 1, 2]
    assert detail["clip_count"] == 3
    first = detail["items"][0]["clip"]
    assert (first["id"], first["project_id"], first["title"]) == (
        b,
        second_project,
        "B",
    )
    assert (first["status"], first["overall"]) == ("rendered", 90)
    assert (first["start"], first["end"]) == (10.0, 12.5)


def test_an_unknown_clip_adds_nothing(client: TestClient, api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 70)
    collection = make(client)
    url = f"/api/collections/{collection['id']}/items"

    message = assert_error(
        client.post(url, json={"clip_ids": [clip_id, 998, 999]}), 404, "not_found"
    )

    assert "998, 999" in message
    assert client.get(f"/api/collections/{collection['id']}").json()["items"] == []
    assert_error(
        client.post("/api/collections/42/items", json={"clip_ids": [1]}),
        404,
        "not_found",
    )
    for body in ({"clip_ids": []}, {}, {"clip_ids": ["x"]}):
        assert_error(client.post(url, json=body), 422, "validation_error")


def test_a_clip_can_be_removed_and_the_rest_keep_their_order(
    client: TestClient, api_engine: Engine
) -> None:
    project = add_project(api_engine)
    a, b, c = (add_clip(api_engine, project, "candidate", 70) for _ in range(3))
    collection = make(client)
    base = f"/api/collections/{collection['id']}"
    client.post(f"{base}/items", json={"clip_ids": [a, b, c]})

    detail = client.delete(f"{base}/items/{b}").json()

    assert ids(detail) == [a, c]
    assert [item["position"] for item in detail["items"]] == [0, 1]
    assert_error(client.delete(f"{base}/items/{b}"), 404, "not_found")
    assert_error(client.delete(f"/api/collections/42/items/{a}"), 404, "not_found")
    again = client.post(f"{base}/items", json={"clip_ids": [b]}).json()
    assert ids(again) == [a, c, b]


def test_deleting_a_collection_or_a_clip_keeps_the_rest(
    client: TestClient, api_engine: Engine
) -> None:
    project = add_project(api_engine)
    a, b = (
        add_clip(api_engine, project, "candidate", 70),
        add_clip(api_engine, project, "candidate", 60),
    )
    kept, dropped = make(client, "Kept"), make(client, "Dropped")
    for collection in (kept, dropped):
        client.post(
            f"/api/collections/{collection['id']}/items", json={"clip_ids": [a, b]}
        )

    assert client.delete(f"/api/collections/{dropped['id']}").status_code == 204
    assert client.delete(f"/api/clips/{a}").status_code == 204

    assert ids(client.get(f"/api/collections/{kept['id']}").json()) == [b]
    assert_error(client.get(f"/api/collections/{dropped['id']}"), 404, "not_found")
    assert_error(client.delete(f"/api/collections/{dropped['id']}"), 404, "not_found")
    assert client.get(f"/api/clips/{b}").status_code == 200


def test_a_collection_needs_a_name(client: TestClient) -> None:
    collection = make(client)

    for body in ({}, {"name": ""}, {"name": "   "}, {"name": "x" * 101}):
        assert_error(
            client.post("/api/collections", json=body), 422, "validation_error"
        )
    for body in ({"name": " "}, {"description": "x" * 501}):
        response = client.patch(f"/api/collections/{collection['id']}", json=body)
        assert_error(response, 422, "validation_error")
    assert_error(
        client.patch("/api/collections/42", json={"name": "x"}), 404, "not_found"
    )
    assert_error(client.get("/api/collections/x"), 422, "validation_error")


def test_the_zip_holds_the_rendered_clips_and_a_manifest(
    client: TestClient, api_engine: Engine
) -> None:
    first_project, second_project = add_project(api_engine), add_project(api_engine)
    a = rendered(api_engine, first_project, "Alpha")
    b = rendered(api_engine, second_project, "Beta", overall=95)
    draft = add_clip(api_engine, first_project, "candidate", 60, "Draft")
    gone = add_clip(api_engine, first_project, "rendered", 60, "Gone")
    collection = make(client, "Best of", description="Picks")
    client.post(
        f"/api/collections/{collection['id']}/items",
        json={"clip_ids": [b, draft, a, gone]},
    )

    response = client.get(f"/api/collections/{collection['id']}/download.zip")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        f'filename="clipforge-collection-{collection["id"]}.zip"'
        in response.headers["content-disposition"]
    )
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert archive.read(f"{b}.mp4") == b"video of Beta"
        manifest = CollectionManifest.model_validate(
            json.loads(archive.read("manifest.json"))
        )
    assert names == [
        f"{b}.mp4",
        f"{b}.srt",
        f"{b}.json",
        f"{a}.mp4",
        f"{a}.srt",
        f"{a}.json",
        "manifest.json",
    ]
    assert (manifest.collection_id, manifest.name) == (collection["id"], "Best of")
    assert manifest.description == "Picks"
    assert [(c.clip_id, c.project_id, c.file) for c in manifest.clips] == [
        (b, second_project, f"{b}.mp4"),
        (a, first_project, f"{a}.mp4"),
    ]
    assert manifest.clips[0].title == "Beta" and manifest.clips[0].overall == 95
    assert [(s.clip_id, s.reason) for s in manifest.skipped] == [
        (draft, "not rendered"),
        (gone, "its rendered video is missing"),
    ]


def test_the_zip_needs_a_rendered_clip(client: TestClient, api_engine: Engine) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 70)
    collection = make(client)
    url = f"/api/collections/{collection['id']}/download.zip"

    assert "no rendered clips" in assert_error(client.get(url), 409, "conflict")
    client.post(
        f"/api/collections/{collection['id']}/items", json={"clip_ids": [clip_id]}
    )
    assert "no rendered clips" in assert_error(client.get(url), 409, "conflict")
    assert_error(client.get("/api/collections/42/download.zip"), 404, "not_found")
