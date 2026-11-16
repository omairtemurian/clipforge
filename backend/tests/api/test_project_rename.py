"""PATCH /projects/{id} {"title"}: rename a project (Projects page kebab)."""

import pytest
from apihelpers import assert_error
from clipforge.models import PROJECT_TITLE_MAX
from fastapi.testclient import TestClient
from seed import add_project
from sqlalchemy import Engine


def test_patch_renames_the_project_and_trims_the_title(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)

    response = client.patch(
        f"/api/projects/{project_id}", json={"title": "  Late night set  "}
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Late night set"
    stored = client.get(f"/api/projects/{project_id}").json()
    assert stored["title"] == "Late night set"
    assert stored["settings"]["aspect"] == "9:16"


@pytest.mark.parametrize("title", ["", "   ", "x" * (PROJECT_TITLE_MAX + 1)])
def test_patch_refuses_a_blank_or_too_long_title(
    client: TestClient, api_engine: Engine, title: str
) -> None:
    project_id = add_project(api_engine)

    response = client.patch(f"/api/projects/{project_id}", json={"title": title})

    assert_error(response, 422, "validation_error")
    assert client.get(f"/api/projects/{project_id}").json()["title"] == "talk"


def test_patch_of_a_missing_project_is_404(client: TestClient) -> None:
    response = client.patch("/api/projects/99", json={"title": "New"})

    assert_error(response, 404, "not_found")
