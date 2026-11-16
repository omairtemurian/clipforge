"""Source rights and credit line in the project API, and rights_ok (TASK-58)."""

import pytest
from apihelpers import assert_error
from clipforge.models import Project
from clipforge.rights import rights_ok
from fastapi.testclient import TestClient
from seed import add_project
from sqlalchemy import Engine

URL = "https://www.youtube.com/watch?v=abc"
RIGHTS = ["own", "permission", "cc_by", "public_domain", "other"]


def test_a_new_project_has_no_rights(client: TestClient) -> None:
    project = client.post("/api/projects", json={"url": URL}).json()

    assert project["source_rights"] is None
    assert project["credit_line"] == ""
    assert project["rights_set"] is False


def test_post_stores_the_rights_and_credit_line(client: TestClient) -> None:
    response = client.post(
        "/api/projects",
        json={"url": URL, "source_rights": "cc_by", "credit_line": "Ann, CC BY"},
    )

    assert response.status_code == 201
    created = response.json()
    assert (created["source_rights"], created["credit_line"]) == ("cc_by", "Ann, CC BY")
    assert created["rights_set"] is True
    assert client.get(f"/api/projects/{created['id']}").json() == created


def test_upload_stores_the_rights_and_credit_line(client: TestClient) -> None:
    response = client.post(
        "/api/projects/upload",
        files={"file": ("talk.mp4", b"video", "video/mp4")},
        data={"source_rights": "own", "credit_line": "Me"},
    )

    assert response.status_code == 201
    project = response.json()
    assert (project["source_rights"], project["credit_line"]) == ("own", "Me")


@pytest.mark.parametrize(
    "body",
    [
        {"url": URL, "source_rights": "stolen"},
        {"url": URL, "source_rights": 3},
        {"url": URL, "credit_line": "x" * 201},
    ],
)
def test_post_rejects_a_bad_value(client: TestClient, body: dict[str, object]) -> None:
    response = client.post("/api/projects", json=body)

    assert "body." in assert_error(response, 422, "validation_error")
    assert client.get("/api/projects").json() == []


def test_upload_rejects_a_bad_enum(client: TestClient) -> None:
    response = client.post(
        "/api/projects/upload",
        files={"file": ("talk.mp4", b"video", "video/mp4")},
        data={"source_rights": "stolen"},
    )

    assert_error(response, 422, "validation_error")
    assert client.get("/api/projects").json() == []


@pytest.mark.parametrize("rights", RIGHTS)
def test_patch_sets_every_rights_value(
    client: TestClient, api_engine: Engine, rights: str
) -> None:
    project_id = add_project(api_engine)

    response = client.patch(
        f"/api/projects/{project_id}",
        json={"source_rights": rights, "credit_line": "Credit"},
    )

    assert response.status_code == 200
    stored = client.get(f"/api/projects/{project_id}").json()
    assert (stored["source_rights"], stored["credit_line"]) == (rights, "Credit")
    assert stored["rights_set"] is True


def test_patch_changes_only_the_fields_sent(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    client.patch(
        f"/api/projects/{project_id}",
        json={"source_rights": "own", "credit_line": "Me"},
    )

    client.patch(f"/api/projects/{project_id}", json={"credit_line": "Us"})
    after_credit = client.get(f"/api/projects/{project_id}").json()
    client.patch(f"/api/projects/{project_id}", json={"brand_template_id": None})
    after_brand = client.get(f"/api/projects/{project_id}").json()

    assert (after_credit["source_rights"], after_credit["credit_line"]) == ("own", "Us")
    assert (after_brand["source_rights"], after_brand["credit_line"]) == ("own", "Us")


def test_patch_with_null_rights_unsets_them(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    client.patch(f"/api/projects/{project_id}", json={"source_rights": "own"})

    response = client.patch(f"/api/projects/{project_id}", json={"source_rights": None})

    assert response.json()["rights_set"] is False


@pytest.mark.parametrize(
    "body", [{"source_rights": "stolen"}, {"credit_line": "x" * 201}]
)
def test_patch_rejects_a_bad_value(
    client: TestClient, api_engine: Engine, body: dict[str, object]
) -> None:
    project_id = add_project(api_engine)

    response = client.patch(f"/api/projects/{project_id}", json=body)

    assert_error(response, 422, "validation_error")
    assert client.get(f"/api/projects/{project_id}").json()["source_rights"] is None


def test_rights_ok_is_false_until_the_rights_are_set(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    unset = Project.model_validate(client.get(f"/api/projects/{project_id}").json())
    client.patch(f"/api/projects/{project_id}", json={"source_rights": "other"})
    chosen = Project.model_validate(client.get(f"/api/projects/{project_id}").json())

    assert rights_ok(unset) is False
    assert rights_ok(chosen) is True
