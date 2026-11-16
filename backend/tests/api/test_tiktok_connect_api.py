"""Tests for connecting a TikTok account through the account endpoints
(clipforge.api.accounts with the TikTok publisher): the TikTok app it
needs ("needs credentials" without it), the authorize URL of TikTok's
desktop Login Kit (client_key, comma-separated scopes, hex PKCE challenge)
and the callback that names the account (user/info) and stores its
restrictions (creator_info), all against recorded answers (respx)."""

import hashlib
from urllib.parse import parse_qs, urlsplit

import httpx
import respx
from apihelpers import assert_error
from clipforge.publishers import tiktok
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from tiktok_publish_fakes import (
    CLIENT_KEY,
    CLIENT_SECRET,
    OPEN_ID,
    answer,
    configure_tiktok,
)

CALLBACK = "http://testserver/api/accounts/tiktok/callback"


def test_tiktok_needs_its_app_keys(
    client: TestClient, monkeypatch: MonkeyPatch
) -> None:
    configure_tiktok(monkeypatch, "")
    statuses = {s["platform"]: s for s in client.get("/api/accounts/platforms").json()}
    assert statuses["tiktok"] == {
        "platform": "tiktok",
        "supported": True,
        "configured": False,
        "settings_keys": ["TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET"],
    }

    message = assert_error(
        client.post("/api/accounts/tiktok/connect"), 412, "needs_credentials"
    )

    assert "TIKTOK_CLIENT_KEY" in message and "TIKTOK_CLIENT_SECRET" in message


def connect(client: TestClient) -> dict[str, list[str]]:
    """Start the TikTok sign-in; return the authorize URL's query."""
    url = client.post("/api/accounts/tiktok/connect").json()["authorize_url"]
    assert url.startswith(tiktok.AUTHORIZE_URL + "?")
    return parse_qs(urlsplit(url).query)


def test_an_account_is_connected_with_its_restrictions(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_tiktok(monkeypatch)
    token = respx_mock.post(tiktok.TOKEN_URL).mock(return_value=answer(200, "token"))
    user = respx_mock.get(tiktok.USER_INFO_URL).mock(
        return_value=answer(200, "user_info")
    )
    respx_mock.post(tiktok.CREATOR_INFO_URL).mock(
        return_value=answer(200, "creator_info_private")
    )

    query = connect(client)
    page = client.get(
        "/api/accounts/tiktok/callback",
        params={"state": query["state"][0], "code": "code-1", "scopes": "a,b"},
    )

    form = dict(httpx.QueryParams(token.calls.last.request.content.decode()))
    verifier = form["code_verifier"]
    assert {k: v[0] for k, v in query.items() if k != "state"} == {
        "client_key": CLIENT_KEY,
        "redirect_uri": CALLBACK,
        "response_type": "code",
        "scope": "user.info.basic,video.publish",
        "code_challenge": hashlib.sha256(verifier.encode()).hexdigest(),
        "code_challenge_method": "S256",
    }
    assert page.status_code == 200
    assert "Clip Lab (@cliplab) is connected" in page.text
    assert form == {
        "grant_type": "authorization_code",
        "code": "code-1",
        "code_verifier": verifier,
        "redirect_uri": CALLBACK,
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
    }
    assert user.calls.last.request.url.params["fields"] == tiktok.USER_FIELDS
    [account] = client.get("/api/accounts", params={"platform": "tiktok"}).json()
    assert (account["external_id"], account["display_name"]) == (
        OPEN_ID,
        "Clip Lab (@cliplab)",
    )
    assert account["scopes"] == ["user.info.basic", "video.publish"]
    assert account["restrictions"] == [
        tiktok.UNAUDITED,
        tiktok.POSTING_CAP,
        "The TikTok account is private.",
        "Who can see posts of this account: followers, friends, only me.",
        "Longest video this account can post: 2 s.",
        "The account turned off comments, Duets, Stitches.",
    ]
    assert "act.cliplab" not in str(account)


def test_a_refused_publish_scope_is_shown_as_a_restriction(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_tiktok(monkeypatch)
    respx_mock.post(tiktok.TOKEN_URL).mock(
        return_value=httpx.Response(
            200, json=answer(200, "token").json() | {"scope": "user.info.basic"}
        )
    )
    respx_mock.get(tiktok.USER_INFO_URL).mock(return_value=answer(200, "user_info"))
    creator = respx_mock.post(tiktok.CREATOR_INFO_URL)

    query = connect(client)
    page = client.get(
        "/api/accounts/tiktok/callback",
        params={"state": query["state"][0], "code": "code-2"},
    )

    assert page.status_code == 200
    assert not creator.called
    [account] = client.get("/api/accounts").json()
    assert account["display_name"] == "Clip Lab"
    assert "video.publish" in account["restrictions"][-1]


def test_a_daily_cap_at_sign_in_still_connects(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_tiktok(monkeypatch)
    respx_mock.post(tiktok.TOKEN_URL).mock(return_value=answer(200, "token"))
    respx_mock.get(tiktok.USER_INFO_URL).mock(return_value=answer(200, "user_info"))
    respx_mock.post(tiktok.CREATOR_INFO_URL).mock(
        return_value=answer(200, "creator_info_post_cap")
    )

    query = connect(client)
    client.get(
        "/api/accounts/tiktok/callback",
        params={"state": query["state"][0], "code": "code-3"},
    )

    [account] = client.get("/api/accounts").json()
    assert "daily post cap" in account["restrictions"][-1]


def test_a_refused_user_info_connects_nothing(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_tiktok(monkeypatch)
    respx_mock.post(tiktok.TOKEN_URL).mock(return_value=answer(200, "token"))
    respx_mock.get(tiktok.USER_INFO_URL).mock(
        return_value=answer(429, "error_rate_limit")
    )

    query = connect(client)
    page = client.get(
        "/api/accounts/tiktok/callback",
        params={"state": query["state"][0], "code": "code-4"},
    )

    assert page.status_code == 400
    assert client.get("/api/accounts").json() == []


def test_a_token_error_in_a_200_answer_connects_nothing(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_tiktok(monkeypatch)
    respx_mock.post(tiktok.TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "error": "invalid_request",
                "error_description": "Code verifier or code challenge is invalid.",
            },
        )
    )

    query = connect(client)
    page = client.get(
        "/api/accounts/tiktok/callback",
        params={"state": query["state"][0], "code": "code-5"},
    )

    assert page.status_code == 400
    assert "Code verifier or code challenge is invalid." in page.text
