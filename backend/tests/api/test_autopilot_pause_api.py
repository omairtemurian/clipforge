"""Tests of GET /api/autopilot/status and PUT /api/autopilot/pause (SPEC-v2
3.19): the global "Pause all autopilot", the campaigns whose autopilot is
stopped, and that only the owner may resume (an API key or agent gets 403)."""

from apihelpers import assert_error
from campaign_api import CAMPAIGNS, add
from fastapi.testclient import TestClient

STATUS = "/api/autopilot/status"
PAUSE = "/api/autopilot/pause"


def test_nothing_is_paused_or_stopped_at_first(client: TestClient) -> None:
    assert client.get(STATUS).json() == {
        "paused": False,
        "paused_at": None,
        "stops": [],
    }


def test_the_owner_pauses_and_resumes_every_autopilot(client: TestClient) -> None:
    campaign = add(client)
    client.put(f"{CAMPAIGNS}/{campaign['id']}/autopilot", json={"enabled": True})

    paused = client.put(PAUSE, json={"paused": True})

    assert paused.status_code == 200
    body = paused.json()
    assert body["paused"] is True
    assert body["paused_at"] is not None
    assert body["stops"] == [
        {
            "campaign_id": campaign["id"],
            "reason": "paused",
            "detail": "every autopilot is paused: resume it",
        }
    ]
    assert client.get(STATUS).json() == body

    resumed = client.put(PAUSE, json={"paused": False}).json()

    assert (resumed["paused"], resumed["paused_at"]) == (False, None)
    assert [s["reason"] for s in resumed["stops"]] == ["permission_missing"]


def test_an_agent_may_pause_but_not_resume(client: TestClient) -> None:
    agent = {"x-api-key": "cf_test"}

    assert client.put(PAUSE, json={"paused": True}, headers=agent).status_code == 200
    response = client.put(PAUSE, json={"paused": False}, headers=agent)

    assert_error(response, 403, "human_only")
    assert client.get(STATUS).json()["paused"] is True


def test_the_body_is_checked(client: TestClient) -> None:
    assert client.put(PAUSE, json={}).status_code == 422
    assert client.put(PAUSE, json={"paused": True, "x": 1}).status_code == 422
