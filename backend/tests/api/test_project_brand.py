"""PATCH /projects/{id}: the brand template of a project's clips (TASK-45)."""

from apihelpers import assert_error
from clipforge.db import BrandTemplateRow
from fastapi.testclient import TestClient
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session


def add_brand(engine: Engine) -> int:
    """Add a brand template and return its id."""
    with Session(engine) as session:
        brand = BrandTemplateRow(
            name="Acme",
            logo_path="/brand/1/logo.png",
            logo_position="br",
            logo_opacity=0.8,
            font="Inter Bold",
            primary_color="#FF6B35",
        )
        session.add(brand)
        session.commit()
        assert brand.id is not None
        return brand.id


def test_patch_sets_then_clears_the_brand_template(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)
    brand_id = add_brand(api_engine)

    response = client.patch(
        f"/api/projects/{project_id}", json={"brand_template_id": brand_id}
    )

    assert response.status_code == 200
    assert response.json()["settings"]["brand_template_id"] == brand_id
    stored = client.get(f"/api/projects/{project_id}").json()
    assert stored["settings"]["brand_template_id"] == brand_id
    assert stored["settings"]["aspect"] == "9:16"

    response = client.patch(
        f"/api/projects/{project_id}", json={"brand_template_id": None}
    )

    assert response.json()["settings"]["brand_template_id"] is None


def test_patch_with_an_unknown_template_is_422(
    client: TestClient, api_engine: Engine
) -> None:
    project_id = add_project(api_engine)

    response = client.patch(
        f"/api/projects/{project_id}", json={"brand_template_id": 99}
    )

    assert "not found" in assert_error(response, 422, "validation_error")


def test_patch_of_an_unknown_project_is_404(client: TestClient) -> None:
    response = client.patch("/api/projects/99", json={"brand_template_id": None})

    assert_error(response, 404, "not_found")


def test_patch_without_the_field_is_422(client: TestClient, api_engine: Engine) -> None:
    project_id = add_project(api_engine)

    response = client.patch(f"/api/projects/{project_id}", json={})

    assert_error(response, 422, "validation_error")
