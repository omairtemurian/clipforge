"""Tests of the submission endpoints (GET/PATCH /api/submissions,
clipforge.api.submissions): the tracker list with copy text, ticking a post
as submitted and the board's answer."""

from typing import Any

from apihelpers import assert_error
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from submission_fakes import URL, account, campaign_clip, new_campaign, publish

SUBMISSIONS = "/api/submissions"


def tracked(client: TestClient, api_engine: Engine, **fields: Any) -> dict[str, Any]:
    """Publish a post of a clip of a new campaign and return its submission."""
    campaign = new_campaign(api_engine, **fields)
    publish(api_engine, campaign_clip(api_engine, campaign.id), account(api_engine))
    (view,) = client.get(SUBMISSIONS).json()
    return dict(view)


def test_the_tracker_lists_the_published_posts_with_the_copy_text(
    client: TestClient, api_engine: Engine
) -> None:
    view = tracked(client, api_engine)

    assert view["status"] == "not_submitted"
    assert view["post_url"] == URL
    assert view["campaign_name"] == "Pizza Clips"
    assert view["copy_text"].startswith(f"{URL}\n")
    assert "Credit line: Clip of Chef Mario" in view["copy_text"]
    assert "Hashtags: #pizza #clips" in view["copy_text"]


def test_an_empty_tracker_is_an_empty_list(client: TestClient) -> None:
    assert client.get(SUBMISSIONS).json() == []


def test_the_list_filters_by_campaign_and_status(
    client: TestClient, api_engine: Engine
) -> None:
    view = tracked(client, api_engine)

    assert (
        len(client.get(SUBMISSIONS, params={"campaign_id": view["campaign_id"]}).json())
        == 1
    )
    assert client.get(SUBMISSIONS, params={"campaign_id": 999}).json() == []
    assert client.get(SUBMISSIONS, params={"status": "paid"}).json() == []
    assert_error(
        client.get(SUBMISSIONS, params={"status": "bogus"}), 422, "validation_error"
    )


def test_ticking_a_post_as_submitted_then_the_boards_answer(
    client: TestClient, api_engine: Engine
) -> None:
    view = tracked(client, api_engine)
    url = f"{SUBMISSIONS}/{view['id']}"

    ticked = client.patch(url, json={"status": "submitted"})
    assert ticked.status_code == 200
    assert ticked.json()["status"] == "submitted"
    assert ticked.json()["submitted_at"] is not None

    approved = client.patch(
        url, json={"status": "approved", "approved_views": 12000, "notes": "ok"}
    )
    assert approved.json()["approved_views"] == 12000

    paid = client.patch(url, json={"status": "paid", "payout_usd": 18.0})
    assert (paid.json()["status"], paid.json()["payout_usd"]) == ("paid", 18.0)
    assert client.get(url).json() == paid.json()


def test_an_illegal_move_is_a_409(client: TestClient, api_engine: Engine) -> None:
    view = tracked(client, api_engine)

    response = client.patch(f"{SUBMISSIONS}/{view['id']}", json={"status": "paid"})

    assert "not_submitted" in assert_error(response, 409, "illegal_submission_move")
    assert client.get(f"{SUBMISSIONS}/{view['id']}").json()["status"] == "not_submitted"


def test_a_bad_patch_is_a_422(client: TestClient, api_engine: Engine) -> None:
    url = f"{SUBMISSIONS}/{tracked(client, api_engine)['id']}"

    for body in ({}, {"approved_views": -1}, {"payout_usd": -1}, {"status": "bogus"}):
        assert_error(client.patch(url, json=body), 422, "validation_error")


def test_an_unknown_submission_is_a_404(client: TestClient) -> None:
    assert_error(client.get(f"{SUBMISSIONS}/5"), 404, "not_found")
    assert_error(
        client.patch(f"{SUBMISSIONS}/5", json={"notes": "x"}), 404, "not_found"
    )
