"""Helpers of the campaign API tests (tests only)."""

from typing import Any

from clipforge.api.campaign_rules import require_campaign_rules
from clipforge.api.campaigns import require_campaign_permission
from clipforge.db import ProjectRow
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session

CAMPAIGNS = "/api/campaigns"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PERMISSION_URL = "https://example.com/creator/clipping-allowed"


def add(client: TestClient, **body: Any) -> dict[str, Any]:
    response = client.post(CAMPAIGNS, json={"name": "Clips", **body})
    assert response.status_code == 201, response.text
    campaign: dict[str, Any] = response.json()
    return campaign


def upload(client: TestClient, campaign_id: int, data: bytes = PNG) -> Any:
    return client.post(
        f"{CAMPAIGNS}/{campaign_id}/permission-screenshot",
        files={"file": ("proof.png", data, "image/png")},
    )


def in_campaign(engine: Engine, campaign_id: int | None) -> int:
    """Add a project that belongs to campaign_id and return its id."""
    project_id = add_project(engine)
    with Session(engine) as session:
        row = session.get(ProjectRow, project_id)
        assert row is not None
        row.campaign_id = campaign_id
        session.add(row)
        session.commit()
    return project_id


def publish_app(client: TestClient) -> TestClient:
    """The app of client with a stand-in publish endpoint behind the
    permission guard, as the publish and schedule endpoints use it."""
    router = APIRouter()

    @router.post(
        "/api/test-publish/{project_id}",
        dependencies=[Depends(require_campaign_permission)],
    )
    def publish(project_id: int) -> dict[str, bool]:
        return {"published": True}

    app: FastAPI = client.app  # type: ignore[assignment]
    app.include_router(router)
    return client


def rules_publish_app(client: TestClient) -> TestClient:
    """The app of client with a stand-in endpoint that publishes a clip on a
    platform behind the campaign rule guard, as the publish endpoints use
    it."""
    router = APIRouter()

    @router.post(
        "/api/test-publish-clip/{clip_id}",
        dependencies=[Depends(require_campaign_rules)],
    )
    def publish(clip_id: int) -> dict[str, bool]:
        return {"published": True}

    app: FastAPI = client.app  # type: ignore[assignment]
    app.include_router(router)
    return client
