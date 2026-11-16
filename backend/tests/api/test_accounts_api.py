"""Tests for the social account endpoints (clipforge.api.accounts): platform
status, the OAuth connect flow with a made-up platform's publisher (its
token endpoint and API answered by respx), several accounts per platform,
disconnecting, and that no token reaches a page, a row or a log."""

import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from apihelpers import assert_error
from clipforge import posts
from clipforge.publishers import registry
from clipforge.token_store import TokenStore
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from social_fakes import (
    ACCESS,
    CLIENT,
    ME_URL,
    REFRESH,
    me_answer,
    register_example,
    token_answer,
)
from sqlalchemy import Engine

CALLBACK = "http://testserver/api/accounts/tiktok/callback"


@pytest.fixture
def example(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The client of an app whose "tiktok" publisher is ExamplePublisher."""
    register_example(monkeypatch)
    return client


def connect(
    client: TestClient, respx_mock: respx.MockRouter, external_id: str, name: str
) -> str:
    """Run the sign-in of an account; return the callback page's text."""
    respx_mock.post(CLIENT.token_url).mock(return_value=token_answer())
    respx_mock.get(ME_URL).mock(return_value=me_answer(external_id, name))
    response = client.post("/api/accounts/tiktok/connect")
    assert response.status_code == 200
    query = parse_qs(urlsplit(response.json()["authorize_url"]).query)
    assert query["redirect_uri"] == [CALLBACK]
    assert query["scope"] == ["video.upload user.info"]
    assert query["code_challenge_method"] == ["S256"]
    page = client.get(
        "/api/accounts/tiktok/callback",
        params={"state": query["state"][0], "code": "c-1"},
    )
    assert page.status_code == 200
    return page.text


def test_platforms_say_which_can_be_used(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "ENTRIES", {})
    register_example(monkeypatch, configured=False)

    statuses = client.get("/api/accounts/platforms").json()

    assert [s["platform"] for s in statuses] == [
        "youtube",
        "tiktok",
        "instagram",
        "facebook",
        "x",
        "linkedin",
    ]
    by_platform = {s["platform"]: (s["supported"], s["configured"]) for s in statuses}
    assert by_platform["tiktok"] == (True, False)
    assert by_platform["youtube"] == (False, False)
    keys = {s["platform"]: s["settings_keys"] for s in statuses}
    assert keys["tiktok"] == ["EXAMPLE_CLIENT_ID"]
    assert keys["youtube"] == []


def test_connect_needs_a_publisher_and_its_oauth_app(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(registry, "ENTRIES", {})
    assert_error(client.post("/api/accounts/tiktok/connect"), 501, "not_supported")
    register_example(monkeypatch, configured=False)
    message = assert_error(
        client.post("/api/accounts/tiktok/connect"), 412, "needs_credentials"
    )
    assert "EXAMPLE_CLIENT_ID" in message
    assert client.post("/api/accounts/myspace/connect").status_code == 422


def test_connected_accounts_are_listed_and_tokens_stored_encrypted(
    example: TestClient,
    respx_mock: respx.MockRouter,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)

    page = connect(example, respx_mock, "acct-1", "Main channel")
    connect(example, respx_mock, "acct-2", "Second channel")
    connect(example, respx_mock, "acct-1", "Main channel renamed")

    assert "Main channel is connected" in page
    accounts = example.get("/api/accounts").json()
    assert [(a["external_id"], a["display_name"]) for a in accounts] == [
        ("acct-1", "Main channel renamed"),
        ("acct-2", "Second channel"),
    ]
    assert accounts[0]["scopes"] == ["video.upload", "user.info"]
    assert example.get("/api/accounts", params={"platform": "youtube"}).json() == []
    me = next(call.request for call in respx_mock.calls if call.request.url == ME_URL)
    assert me.headers["authorization"] == "Bearer " + ACCESS
    store = TokenStore.from_settings()
    for account in accounts:
        token = store.load(account["token_ref"])
        assert token is not None and token.refresh_token == REFRESH
    for secret in (ACCESS, REFRESH):
        assert secret not in page
        assert secret not in caplog.text
        assert secret not in example.get("/api/accounts").text


def test_callback_failures_connect_nothing(
    example: TestClient, respx_mock: respx.MockRouter
) -> None:
    forged = example.get(
        "/api/accounts/tiktok/callback", params={"state": "forged", "code": "c"}
    )
    assert forged.status_code == 400

    query = parse_qs(
        urlsplit(
            example.post("/api/accounts/tiktok/connect").json()["authorize_url"]
        ).query
    )
    denied = example.get(
        "/api/accounts/tiktok/callback",
        params={"state": query["state"][0], "error": "access_denied"},
    )
    assert denied.status_code == 400
    assert "access was denied" in denied.text

    respx_mock.post(CLIENT.token_url).mock(return_value=token_answer())
    respx_mock.get(ME_URL).mock(return_value=httpx.Response(500))
    query = parse_qs(
        urlsplit(
            example.post("/api/accounts/tiktok/connect").json()["authorize_url"]
        ).query
    )
    failed = example.get(
        "/api/accounts/tiktok/callback",
        params={"state": query["state"][0], "code": "c"},
    )
    assert failed.status_code == 400
    assert "ExampleTube answered 500" in failed.text
    assert example.get("/api/accounts").json() == []


def test_disconnect_forgets_the_account_and_its_token(
    example: TestClient, respx_mock: respx.MockRouter, api_engine: Engine
) -> None:
    connect(example, respx_mock, "acct-1", "Main")
    (account,) = example.get("/api/accounts").json()
    clip_id = add_clip(api_engine, add_project(api_engine), "rendered", 70)
    post = posts.create_post(
        api_engine, clip_id=clip_id, account_id=account["id"], payload={}
    )

    busy = example.delete(f"/api/accounts/{account['id']}")
    assert "cancel them" in assert_error(busy, 409, "account_busy")
    posts.move(api_engine, post.id, "canceled")

    assert example.delete(f"/api/accounts/{account['id']}").status_code == 204
    assert example.get("/api/accounts").json() == []
    assert TokenStore.from_settings().load(account["token_ref"]) is None
    assert_error(example.delete(f"/api/accounts/{account['id']}"), 404, "not_found")


def test_the_first_account_is_the_default_and_another_can_be_chosen(
    example: TestClient, respx_mock: respx.MockRouter
) -> None:
    connect(example, respx_mock, "acct-1", "Main")
    connect(example, respx_mock, "acct-2", "Side")
    first, second = example.get("/api/accounts").json()
    assert (first["is_default"], second["is_default"]) == (True, False)

    chosen = example.put(f"/api/accounts/{second['id']}/default")

    assert chosen.status_code == 200 and chosen.json()["is_default"] is True
    listed = example.get("/api/accounts").json()
    assert [a["is_default"] for a in listed] == [False, True]
    assert_error(example.put("/api/accounts/99/default"), 404, "not_found")
