"""Tests of the accounts of a campaign and its bulk scheduler
(GET/PUT /api/campaigns/{id}/accounts, POST /api/campaigns/{id}/bulk-schedule,
clipforge.campaign_accounts): a campaign maps to the owner's own accounts and
schedules its clips on them only."""

from typing import Any

from apihelpers import assert_error
from campaign_api import CAMPAIGNS, PERMISSION_URL, add, upload
from clipforge import posts
from fastapi.testclient import TestClient
from post_api_fakes import AGENT
from sqlalchemy import Engine
from submission_fakes import account, campaign_clip

RULES = {
    "timezone": "Europe/Zurich",
    "times": ["09:00"],
    "posts_per_day": 1,
    "skip_days": ["sat", "sun"],
    "start_date": "2030-01-14",
}


def accounts_url(campaign_id: int) -> str:
    return f"{CAMPAIGNS}/{campaign_id}/accounts"


def bulk_url(campaign_id: int) -> str:
    return f"{CAMPAIGNS}/{campaign_id}/bulk-schedule"


def bulk(clip_ids: list[int], **changes: Any) -> dict[str, Any]:
    return {"clip_ids": clip_ids, "rules": RULES} | changes


def test_a_campaign_starts_without_accounts(client: TestClient) -> None:
    campaign = add(client)

    assert client.get(accounts_url(campaign["id"])).json() == []


def test_a_campaign_is_mapped_to_the_owners_accounts(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client)
    youtube = account(api_engine, "youtube")
    tiktok = account(api_engine, "tiktok")

    saved = client.put(
        accounts_url(campaign["id"]), json={"account_ids": [tiktok, youtube, tiktok]}
    )

    assert saved.status_code == 200
    assert [a["id"] for a in saved.json()] == [youtube, tiktok]
    assert client.get(accounts_url(campaign["id"])).json() == saved.json()
    assert "token_ref" in saved.json()[0]


def test_putting_accounts_replaces_the_ones_before(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client)
    youtube = account(api_engine, "youtube")
    tiktok = account(api_engine, "tiktok")
    client.put(accounts_url(campaign["id"]), json={"account_ids": [youtube]})

    client.put(accounts_url(campaign["id"]), json={"account_ids": [tiktok]})

    assert [a["id"] for a in client.get(accounts_url(campaign["id"])).json()] == [
        tiktok
    ]
    client.put(accounts_url(campaign["id"]), json={"account_ids": []})
    assert client.get(accounts_url(campaign["id"])).json() == []


def test_an_account_of_a_platform_the_campaign_does_not_allow_is_refused(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client, allowed_platforms=["youtube"])
    youtube = account(api_engine, "youtube")
    tiktok = account(api_engine, "tiktok")
    client.put(accounts_url(campaign["id"]), json={"account_ids": [youtube]})

    response = client.put(
        accounts_url(campaign["id"]), json={"account_ids": [youtube, tiktok]}
    )

    assert "does not allow" in assert_error(response, 422, "validation_error")
    assert [a["id"] for a in client.get(accounts_url(campaign["id"])).json()] == [
        youtube
    ]


def test_unknown_campaigns_and_accounts_are_404(client: TestClient) -> None:
    assert_error(client.get(accounts_url(9)), 404, "not_found")
    assert_error(
        client.put(accounts_url(9), json={"account_ids": []}), 404, "not_found"
    )
    campaign = add(client)
    assert_error(
        client.put(accounts_url(campaign["id"]), json={"account_ids": [77]}),
        404,
        "not_found",
    )


def test_deleting_an_account_or_a_campaign_removes_the_mapping(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client)
    youtube = account(api_engine, "youtube")
    client.put(accounts_url(campaign["id"]), json={"account_ids": [youtube]})

    assert client.delete(f"{CAMPAIGNS}/{campaign['id']}").status_code == 204

    with api_engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT * FROM campaign_account").all() == []


def test_the_campaign_bulk_scheduler_posts_to_its_accounts_only(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client)
    youtube = account(api_engine, "youtube")
    account(api_engine, "tiktok")
    client.put(accounts_url(campaign["id"]), json={"account_ids": [youtube]})
    clips = [campaign_clip(api_engine, campaign["id"], f"Clip {n}") for n in (1, 2)]

    response = client.post(bulk_url(campaign["id"]), json=bulk(clips), headers=AGENT)

    assert response.status_code == 201, response.text
    created = response.json()
    assert [(p["clip_id"], p["account_id"], p["status"]) for p in created] == [
        (clips[0], youtube, "draft"),
        (clips[1], youtube, "draft"),
    ]
    assert [p["scheduled_at"] for p in created] == [
        "2030-01-14T08:00:00Z",
        "2030-01-15T08:00:00Z",
    ]
    assert len(posts.list_posts(api_engine)) == 2


def test_the_campaign_bulk_scheduler_uses_the_given_text(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client)
    youtube = account(api_engine, "youtube")
    client.put(accounts_url(campaign["id"]), json={"account_ids": [youtube]})
    clip = campaign_clip(api_engine, campaign["id"])

    created = client.post(
        bulk_url(campaign["id"]),
        json=bulk([clip], text={"caption": "Fresh pizza"}),
    ).json()

    assert "Fresh pizza" in created[0]["payload"]["description"]


def test_a_campaign_without_accounts_cannot_bulk_schedule(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client)
    clip = campaign_clip(api_engine, campaign["id"])

    response = client.post(bulk_url(campaign["id"]), json=bulk([clip]))

    assert "no accounts" in assert_error(response, 422, "validation_error")
    assert posts.list_posts(api_engine) == []


def test_clips_of_other_campaigns_are_refused(
    client: TestClient, api_engine: Engine
) -> None:
    campaign, other = add(client), add(client, name="Other")
    youtube = account(api_engine, "youtube")
    client.put(accounts_url(campaign["id"]), json={"account_ids": [youtube]})
    mine = campaign_clip(api_engine, campaign["id"])
    theirs = campaign_clip(api_engine, other["id"])
    free = campaign_clip(api_engine, None)

    response = client.post(bulk_url(campaign["id"]), json=bulk([mine, theirs, free]))

    message = assert_error(response, 422, "validation_error")
    assert str([theirs, free]) in message
    assert posts.list_posts(api_engine) == []


def test_an_unknown_campaign_cannot_bulk_schedule(client: TestClient) -> None:
    assert_error(client.post(bulk_url(9), json=bulk([1])), 404, "not_found")


def test_an_agent_cannot_queue_the_campaigns_posts(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client)
    youtube = account(api_engine, "youtube")
    client.put(accounts_url(campaign["id"]), json={"account_ids": [youtube]})
    clip = campaign_clip(api_engine, campaign["id"])

    response = client.post(
        bulk_url(campaign["id"]), json=bulk([clip], queue=True), headers=AGENT
    )

    assert_error(response, 403, "human_only")
    assert posts.list_posts(api_engine) == []


def test_queuing_needs_the_campaigns_permission_evidence(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(client)
    youtube = account(api_engine, "youtube")
    client.put(accounts_url(campaign["id"]), json={"account_ids": [youtube]})
    clip = campaign_clip(api_engine, campaign["id"])

    response = client.post(bulk_url(campaign["id"]), json=bulk([clip], queue=True))

    assert response.status_code == 409, response.text
    assert posts.list_posts(api_engine) == []


def test_the_owner_queues_the_campaigns_posts_once_it_has_permission(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = add(
        client, permission_source_url=PERMISSION_URL, allowed_platforms=["youtube"]
    )
    assert upload(client, campaign["id"]).status_code == 200
    youtube = account(api_engine, "youtube")
    client.put(accounts_url(campaign["id"]), json={"account_ids": [youtube]})
    clip = campaign_clip(api_engine, campaign["id"])

    response = client.post(bulk_url(campaign["id"]), json=bulk([clip], queue=True))

    assert response.status_code == 201, response.text
    assert [p["status"] for p in response.json()] == ["queued"]
