"""Tests of the Approval Inbox endpoints (SPEC-v2 3.19, api.drafts) in the
owner's app session: the inbox list, making drafts, notes, approving one or
all drafts of a campaign into the next free slots, rejecting, and the
errors. Human-only enforcement is in test_approval_auth.py."""

from apihelpers import assert_error
from clipforge import posts
from clipforge.autopilot import inbox
from draft_fakes import add_draft, inbox_with_draft, postable_campaign
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from submission_fakes import campaign_clip, new_campaign

RULES = {"timezone": "UTC", "times": ["10:00"], "start_date": "2030-02-01"}


def test_approve_all_queues_each_pending_draft_in_the_next_slot(
    client: TestClient, api_engine: Engine
) -> None:
    setup = inbox_with_draft(api_engine, slots=None, max_posts_per_day=1)
    second = add_draft(api_engine, setup.campaign_id, "Second")

    response = client.post(
        f"/api/campaigns/{setup.campaign_id}/drafts/approve", json={"rules": RULES}
    )

    assert response.status_code == 200, response.text
    approvals = response.json()
    assert [a["draft"]["id"] for a in approvals] == [setup.draft_id, second]
    assert [a["draft"]["status"] for a in approvals] == ["approved", "approved"]
    times = [p["scheduled_at"] for a in approvals for p in a["posts"]]
    assert times == ["2030-02-01T10:00:00Z", "2030-02-02T10:00:00Z"]
    assert {p.status for p in posts.list_posts(api_engine)} == {"queued"}


def test_a_decided_draft_cannot_be_decided_again(
    client: TestClient, api_engine: Engine
) -> None:
    setup = inbox_with_draft(api_engine)
    assert client.post(f"/api/drafts/{setup.draft_id}/approve", json={}).is_success

    again = client.post(f"/api/drafts/{setup.draft_id}/approve", json={})
    reject = client.post(f"/api/drafts/{setup.draft_id}/reject", json={})

    assert_error(again, 409, "draft_decided")
    assert_error(reject, 409, "draft_decided")
    assert len(posts.list_posts(api_engine)) == 1


def test_a_needs_fix_draft_is_not_posted_while_its_clip_fails(
    client: TestClient, api_engine: Engine
) -> None:
    campaign = new_campaign(api_engine)
    draft = inbox.create_draft(api_engine, campaign_clip(api_engine, campaign.id))
    assert draft.status == "needs_fix"

    response = client.post(f"/api/drafts/{draft.id}/approve", json={"rules": RULES})

    assert response.status_code == 422, response.text
    assert inbox.get_draft(api_engine, draft.id).status == "needs_fix"
    assert posts.list_posts(api_engine) == []


def test_approving_needs_slots(client: TestClient, api_engine: Engine) -> None:
    setup = inbox_with_draft(api_engine, slots=None)

    response = client.post(f"/api/drafts/{setup.draft_id}/approve", json={})

    assert_error(response, 422, "validation_error")
    assert inbox.get_draft(api_engine, setup.draft_id).status == "pending"


def test_rejecting_keeps_the_reason(client: TestClient, api_engine: Engine) -> None:
    setup = inbox_with_draft(api_engine)

    response = client.post(
        f"/api/drafts/{setup.draft_id}/reject", json={"reason": "too_long"}
    )
    listed = client.get("/api/drafts", params={"campaign_id": setup.campaign_id})

    assert response.status_code == 200, response.text
    assert (response.json()["status"], response.json()["reject_reason"]) == (
        "rejected",
        "too_long",
    )
    assert [d["status"] for d in listed.json()] == ["rejected"]


def test_making_a_draft(client: TestClient, api_engine: Engine) -> None:
    clip_id = campaign_clip(api_engine, postable_campaign(api_engine))
    loose = add_clip(api_engine, add_project(api_engine), "rendered", 70)

    made = client.post("/api/drafts", json={"clip_id": clip_id})

    assert made.status_code == 201, made.text
    assert (made.json()["clip_id"], made.json()["status"]) == (clip_id, "pending")
    assert_error(
        client.post("/api/drafts", json={"clip_id": loose}), 422, "validation_error"
    )
    assert_error(client.post("/api/drafts", json={"clip_id": 999}), 404, "not_found")


def test_unknown_drafts_campaigns_and_blank_notes(
    client: TestClient, api_engine: Engine
) -> None:
    setup = inbox_with_draft(api_engine)

    assert_error(client.get("/api/drafts/999"), 404, "not_found")
    assert_error(client.post("/api/drafts/999/approve", json={}), 404, "not_found")
    assert_error(client.post("/api/drafts/999/reject", json={}), 404, "not_found")
    assert_error(
        client.post("/api/drafts/999/notes", json={"text": "x"}), 404, "not_found"
    )
    assert_error(
        client.post("/api/campaigns/999/drafts/approve", json={}), 404, "not_found"
    )
    blank = client.post(f"/api/drafts/{setup.draft_id}/notes", json={"text": "  "})
    assert blank.status_code == 422
