"""Tests of the owner's API key endpoints (/api/api-keys) and of the keys
on /api/v1: shown once, stored hashed, last use recorded, revocable, and
never made or listed by an agent."""

import hashlib

import pytest
from api_key_fakes import make_key
from apihelpers import assert_error
from clipforge.api_keys import KEY_PREFIX, PREFIX_LENGTH
from fastapi.testclient import TestClient
from sqlalchemy import Engine


def test_a_new_key_is_shown_once_and_stored_hashed(
    client: TestClient, api_engine: Engine
) -> None:
    response = client.post("/api/api-keys", json={"name": "  n8n  "})

    assert response.status_code == 201
    created = response.json()
    key = created["key"]
    assert key.startswith(KEY_PREFIX) and len(key) == len(KEY_PREFIX) + 43
    assert created["name"] == "n8n"
    assert created["prefix"] == key[:PREFIX_LENGTH]
    assert created["last_used_at"] is None
    listed = client.get("/api/api-keys").json()
    assert listed == [{k: v for k, v in created.items() if k != "key"}]
    with api_engine.connect() as conn:
        rows = conn.exec_driver_sql("SELECT * FROM api_key").fetchall()
    assert len(rows) == 1
    assert key not in [str(value) for value in rows[0]]
    stored_hash = rows[0][-1]
    assert stored_hash == hashlib.sha256(key.encode()).hexdigest()


def test_every_key_is_different(client: TestClient) -> None:
    assert make_key(client, "a") != make_key(client, "b")


def test_a_used_key_records_when(client: TestClient, api_key: str) -> None:
    response = client.get("/api/v1/projects", headers={"X-API-Key": api_key})

    assert response.status_code == 200
    (listed,) = client.get("/api/api-keys").json()
    assert listed["last_used_at"] is not None
    assert listed["last_used_at"].endswith("Z")


def test_a_revoked_key_is_401(client: TestClient, api_key: str) -> None:
    (listed,) = client.get("/api/api-keys").json()

    deleted = client.delete(f"/api/api-keys/{listed['id']}")
    response = client.get("/api/v1/projects", headers={"X-API-Key": api_key})

    assert deleted.status_code == 204
    assert_error(response, 401, "api_key_invalid")
    assert client.get("/api/api-keys").json() == []
    assert_error(client.delete(f"/api/api-keys/{listed['id']}"), 404, "not_found")


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_a_key_needs_a_name(client: TestClient, name: str) -> None:
    response = client.post("/api/api-keys", json={"name": name})

    assert_error(response, 422, "validation_error")


def test_an_agent_cannot_make_list_or_revoke_keys(
    client: TestClient, agent: dict[str, str]
) -> None:
    (listed,) = client.get("/api/api-keys").json()
    bearer = {"Authorization": f"Bearer {agent['X-API-Key']}"}

    for headers in (agent, bearer):
        made = client.post("/api/api-keys", json={"name": "mine"}, headers=headers)
        assert_error(made, 403, "human_only")
        assert_error(client.get("/api/api-keys", headers=headers), 403, "human_only")
        revoked = client.delete(f"/api/api-keys/{listed['id']}", headers=headers)
        assert_error(revoked, 403, "human_only")
    assert len(client.get("/api/api-keys").json()) == 1


def test_the_apps_own_api_needs_no_key(client: TestClient) -> None:
    assert client.get("/api/projects").status_code == 200
