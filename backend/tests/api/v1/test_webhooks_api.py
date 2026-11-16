"""Tests of the owner's webhook endpoints (/api/webhooks): the secret shown
once, editing, the delivery log, and that no agent can register one."""

import pytest
from apihelpers import assert_error
from clipforge import webhooks
from fastapi.testclient import TestClient
from sqlalchemy import Engine

URL = "https://hooks.example.test/n8n"
BODY = {"url": URL, "events": ["post.published", "clip.rendered"]}


def test_a_new_webhook_shows_its_secret_once(client: TestClient) -> None:
    response = client.post("/api/webhooks", json=BODY)

    assert response.status_code == 201
    created = response.json()
    assert created["secret"].startswith("whsec_")
    assert (created["url"], created["enabled"]) == (URL, True)
    assert created["events"] == ["clip.rendered", "post.published"]
    assert created["created_at"].endswith("Z")
    listed = client.get("/api/webhooks").json()
    assert listed == [{k: v for k, v in created.items() if k != "secret"}]


@pytest.mark.parametrize(
    "body",
    [
        {"url": "ftp://x.test", "events": ["clip.rendered"]},
        {"url": URL, "events": []},
        {"url": URL, "events": ["clip.deleted"]},
        {"url": URL},
    ],
)
def test_a_webhook_needs_an_http_url_and_known_events(
    client: TestClient, body: dict[str, object]
) -> None:
    assert_error(client.post("/api/webhooks", json=body), 422, "validation_error")
    assert client.get("/api/webhooks").json() == []


def test_a_webhook_can_be_changed_paused_and_deleted(client: TestClient) -> None:
    hook = client.post("/api/webhooks", json=BODY).json()
    path = f"/api/webhooks/{hook['id']}"

    patched = client.patch(path, json={"enabled": False, "events": ["post.failed"]})

    assert patched.status_code == 200
    assert patched.json() == {
        **{k: v for k, v in hook.items() if k != "secret"},
        "enabled": False,
        "events": ["post.failed"],
    }
    assert client.delete(path).status_code == 204
    assert client.get("/api/webhooks").json() == []
    for response in (client.patch(path, json={}), client.delete(path)):
        assert_error(response, 404, "not_found")
    assert_error(client.get(f"{path}/deliveries"), 404, "not_found")


def test_the_delivery_log_lists_the_latest_first(
    client: TestClient, api_engine: Engine
) -> None:
    hook = client.post("/api/webhooks", json=BODY).json()
    for number in range(3):
        webhooks.emit(api_engine, "clip.rendered", {"n": number})
    webhooks.emit(api_engine, "post.failed", {})

    log = client.get(f"/api/webhooks/{hook['id']}/deliveries").json()
    limited = client.get(f"/api/webhooks/{hook['id']}/deliveries?limit=2").json()

    assert [entry["data"] for entry in log] == [{"n": 2}, {"n": 1}, {"n": 0}]
    assert log[0].keys() >= {"event", "status", "attempts", "response_status", "error"}
    assert (log[0]["status"], log[0]["attempts"]) == ("pending", 0)
    assert log[0]["created_at"].endswith("Z")
    assert limited == log[:2]
    assert (
        client.get(f"/api/webhooks/{hook['id']}/deliveries?limit=0").status_code == 422
    )


def test_an_agent_cannot_use_the_webhook_endpoints(
    client: TestClient, agent: dict[str, str]
) -> None:
    hook = client.post("/api/webhooks", json=BODY).json()
    path = f"/api/webhooks/{hook['id']}"
    bearer = {"Authorization": "Bearer " + agent["X-API-Key"]}

    for headers in (agent, bearer):
        for response in (
            client.post("/api/webhooks", json=BODY, headers=headers),
            client.get("/api/webhooks", headers=headers),
            client.patch(path, json={"url": "https://evil.test"}, headers=headers),
            client.delete(path, headers=headers),
            client.get(f"{path}/deliveries", headers=headers),
        ):
            assert_error(response, 403, "human_only")
    assert client.get("/api/webhooks").json()[0]["url"] == URL


def test_webhooks_are_not_part_of_the_public_api(
    client: TestClient, api_key: str
) -> None:
    response = client.get("/api/v1/webhooks", headers={"X-API-Key": api_key})

    assert response.status_code == 404
