"""Tests for the permission evidence of a campaign: the screenshot kept as an
asset, and the guard that publishing and scheduling depend on."""

from pathlib import Path

import pytest
from apihelpers import assert_error
from campaign_api import (
    CAMPAIGNS,
    JPEG,
    PERMISSION_URL,
    PNG,
    add,
    in_campaign,
    publish_app,
    upload,
)
from clipforge import assets
from clipforge.db import ProjectRow
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlmodel import Session


def test_a_screenshot_is_kept_as_an_asset_and_sets_the_date(
    client: TestClient, api_engine: Engine, data_dir: Path
) -> None:
    created = add(client, permission_source_url=PERMISSION_URL)

    response = upload(client, created["id"])

    assert response.status_code == 200
    campaign = response.json()
    asset_id = campaign["permission_screenshot_asset_id"]
    with Session(api_engine) as session:
        asset = assets.get_asset(session, asset_id)
    assert asset is not None
    assert (asset.kind, asset.source_url, asset.tags) == (
        "image",
        PERMISSION_URL,
        ["campaign-permission"],
    )
    stored = Path(asset.path)
    assert stored == data_dir / "campaigns" / str(created["id"]) / "permission.png"
    assert stored.read_bytes() == PNG
    assert campaign["permission_complete"] is True
    served = client.get(f"{CAMPAIGNS}/{created['id']}/permission-screenshot")
    assert (served.status_code, served.content) == (200, PNG)
    assert served.headers["content-type"] == "image/png"


def test_a_screenshot_sets_the_date_even_without_a_source_url(
    client: TestClient,
) -> None:
    created = add(client)

    campaign = upload(client, created["id"]).json()

    assert campaign["permission_checked_at"] is not None
    assert campaign["permission_complete"] is False


def test_a_new_screenshot_replaces_the_old_asset_and_file(
    client: TestClient, api_engine: Engine, data_dir: Path
) -> None:
    created = add(client)
    first = upload(client, created["id"]).json()["permission_screenshot_asset_id"]

    second = upload(client, created["id"], JPEG).json()

    assert second["permission_screenshot_asset_id"] != first
    with Session(api_engine) as session:
        assert assets.get_asset(session, first) is None
        kept = assets.list_assets(session, tag="campaign-permission")
    assert [Path(a.path).name for a in kept] == ["permission.jpg"]
    assert sorted(p.name for p in (data_dir / "campaigns" / "1").iterdir()) == [
        "permission.jpg"
    ]


@pytest.mark.parametrize(
    "data", [b"", b"just text, not an image", b"\x89PNG\r\n\x1a\n" + b"0" * 5_300_000]
)
def test_a_screenshot_must_be_a_small_image(client: TestClient, data: bytes) -> None:
    created = add(client)

    assert_error(upload(client, created["id"], data), 422, "validation_error")

    assert client.get(f"{CAMPAIGNS}/{created['id']}").json() == created
    missing = client.get(f"{CAMPAIGNS}/{created['id']}/permission-screenshot")
    assert_error(missing, 404, "not_found")


def test_deleting_a_campaign_removes_its_screenshot_and_frees_its_projects(
    client: TestClient, api_engine: Engine, data_dir: Path
) -> None:
    created = add(client)
    upload(client, created["id"])
    project = in_campaign(api_engine, created["id"])

    assert client.delete(f"{CAMPAIGNS}/{created['id']}").status_code == 204

    assert client.get(CAMPAIGNS).json() == []
    assert not (data_dir / "campaigns" / str(created["id"])).exists()
    with Session(api_engine) as session:
        assert assets.list_assets(session, tag="campaign-permission") == []
        row = session.get(ProjectRow, project)
        assert row is not None and row.campaign_id is None


def test_publishing_is_409_until_url_screenshot_and_date_are_present(
    client: TestClient, api_engine: Engine
) -> None:
    publish_app(client)
    created = add(client)
    project = in_campaign(api_engine, created["id"])
    url = f"/api/test-publish/{project}"
    campaign_url = f"{CAMPAIGNS}/{created['id']}"

    nothing = assert_error(client.post(url), 409, "permission_missing")
    assert "the permission source URL" in nothing
    assert "a screenshot of the permission" in nothing
    assert "the date" in nothing

    client.patch(campaign_url, json={"permission_source_url": PERMISSION_URL})
    only_url = assert_error(client.post(url), 409, "permission_missing")
    assert "a screenshot of the permission" in only_url
    assert "source URL" not in only_url

    upload(client, created["id"])
    assert client.post(url).json() == {"published": True}

    client.patch(campaign_url, json={"permission_source_url": None})
    assert_error(client.post(url), 409, "permission_missing")


def test_only_a_screenshot_is_not_enough_to_publish(
    client: TestClient, api_engine: Engine
) -> None:
    publish_app(client)
    created = add(client)
    upload(client, created["id"])
    project = in_campaign(api_engine, created["id"])

    message = assert_error(
        client.post(f"/api/test-publish/{project}"), 409, "permission_missing"
    )

    assert "the permission source URL" in message


def test_a_project_without_a_campaign_is_not_blocked_by_the_guard(
    client: TestClient, api_engine: Engine
) -> None:
    publish_app(client)
    project = in_campaign(api_engine, None)

    assert client.post(f"/api/test-publish/{project}").status_code == 200
