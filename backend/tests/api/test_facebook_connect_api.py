"""Tests for connecting a Facebook Page through the account endpoints
(clipforge.api.accounts with the Facebook publisher): the Meta app it needs
("needs credentials" without it), the Facebook Login dialog URL
(comma-separated permissions, config_id, PKCE), the callback that trades
the code (GET), exchanges it for a long-lived token, reads the granted
permissions, picks a Page the user can create content on and stores its
restrictions, all against recorded answers (respx)."""

from urllib.parse import parse_qs, urlsplit

import httpx
import respx
from apihelpers import assert_error
from clipforge.publishers import facebook
from clipforge.publishers.facebook_api import PAGES_FIELDS
from clipforge.publishers.meta_graph import PERMISSIONS_URL, TOKEN_URL
from facebook_publish_fakes import PAGE_ID, PAGES_URL, answer
from fastapi.testclient import TestClient
from instagram_publish_fakes import APP_ID, APP_SECRET, CONFIG_ID, configure_meta
from pytest import MonkeyPatch

CALLBACK = "http://testserver/api/accounts/facebook/callback"


def test_facebook_needs_the_meta_app_keys(
    client: TestClient, monkeypatch: MonkeyPatch
) -> None:
    configure_meta(monkeypatch, "")
    statuses = {s["platform"]: s for s in client.get("/api/accounts/platforms").json()}
    assert statuses["facebook"] == {
        "platform": "facebook",
        "supported": True,
        "configured": False,
        "settings_keys": ["META_APP_ID", "META_APP_SECRET"],
    }

    message = assert_error(
        client.post("/api/accounts/facebook/connect"), 412, "needs_credentials"
    )

    assert "META_APP_ID" in message and "META_APP_SECRET" in message


def connect(client: TestClient) -> dict[str, list[str]]:
    """Start the Facebook sign-in; return the dialog URL's query."""
    url = client.post("/api/accounts/facebook/connect").json()["authorize_url"]
    assert url.startswith("https://www.facebook.com/v26.0/dialog/oauth?")
    return parse_qs(urlsplit(url).query)


def mock_sign_in(
    respx_mock: respx.MockRouter, permissions: str = "permissions"
) -> dict[str, respx.Route]:
    """Mock the token trades and the account calls of a sign-in."""
    return {
        "token": respx_mock.get(TOKEN_URL).mock(
            side_effect=[answer(200, "token"), answer(200, "token_long_lived")]
        ),
        "permissions": respx_mock.get(PERMISSIONS_URL).mock(
            return_value=answer(200, permissions)
        ),
        "pages": respx_mock.get(PAGES_URL).mock(return_value=answer(200, "pages")),
    }


def test_a_page_is_connected_with_a_long_lived_token_and_restrictions(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_meta(monkeypatch, config_id=CONFIG_ID)
    routes = mock_sign_in(respx_mock)

    query = connect(client)
    page = client.get(
        "/api/accounts/facebook/callback",
        params={"state": query["state"][0], "code": "code-1"},
    )

    assert page.status_code == 200
    assert "Clip Lab is connected" in page.text
    sent = {k: v[0] for k, v in query.items() if k not in ("state", "code_challenge")}
    assert sent == {
        "client_id": APP_ID,
        "redirect_uri": CALLBACK,
        "response_type": "code",
        "scope": ",".join(facebook.SCOPES),
        "code_challenge_method": "S256",
        "config_id": CONFIG_ID,
    }
    trade, exchange = (c.request for c in routes["token"].calls)
    assert trade.method == "GET" and not trade.content
    assert trade.url.params["client_secret"] == APP_SECRET
    assert trade.url.params["redirect_uri"] == CALLBACK
    assert exchange.url.params["grant_type"] == "fb_exchange_token"
    assert exchange.url.params["fb_exchange_token"] == "EAAcliplab-short-0001"
    pages = routes["pages"].calls.last.request
    assert pages.headers["authorization"] == "Bearer EAAcliplab-long-0001"
    assert pages.url.params["fields"] == PAGES_FIELDS
    [account] = client.get("/api/accounts", params={"platform": "facebook"}).json()
    assert (account["external_id"], account["display_name"]) == (PAGE_ID, "Clip Lab")
    assert account["scopes"] == [*facebook.SCOPES, "public_profile"]
    assert account["restrictions"] == [
        facebook.UNAUDITED,
        facebook.POSTING_CAP,
        facebook.REEL_RULES,
        "Connected Clip Lab; you also manage Clip Lab Shorts (one Page per "
        "connection: choose a single Page in Facebook's permission dialog).",
    ]
    assert "EAAcliplab" not in str(account)


def test_a_declined_publish_permission_is_shown_as_a_restriction(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_meta(monkeypatch)
    mock_sign_in(respx_mock, "permissions_declined")

    query = connect(client)
    page = client.get(
        "/api/accounts/facebook/callback",
        params={"state": query["state"][0], "code": "code-2"},
    )

    assert page.status_code == 200
    assert "config_id" not in query
    [account] = client.get("/api/accounts").json()
    assert "pages_manage_posts" not in account["scopes"]
    assert facebook.SCOPE_MISSING in account["restrictions"]


def test_unknown_permissions_still_connect(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_meta(monkeypatch)
    routes = mock_sign_in(respx_mock)
    routes["permissions"].mock(side_effect=httpx.ConnectError("offline"))

    query = connect(client)
    client.get(
        "/api/accounts/facebook/callback",
        params={"state": query["state"][0], "code": "code-3"},
    )

    [account] = client.get("/api/accounts").json()
    assert account["scopes"] == list(facebook.SCOPES)
    assert facebook.SCOPE_MISSING not in account["restrictions"]


def test_pages_the_user_cannot_create_content_on_connect_nothing(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_meta(monkeypatch)
    routes = mock_sign_in(respx_mock)
    routes["pages"].mock(return_value=answer(200, "pages_stats_only"))

    query = connect(client)
    page = client.get(
        "/api/accounts/facebook/callback",
        params={"state": query["state"][0], "code": "code-4"},
    )

    assert page.status_code == 400
    assert "lets you create content" in page.text
    assert client.get("/api/accounts").json() == []


def test_a_cancelled_dialog_connects_nothing(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_meta(monkeypatch)
    query = connect(client)

    page = client.get(
        "/api/accounts/facebook/callback",
        params={
            "state": query["state"][0],
            "error": "access_denied",
            "error_reason": "user_denied",
        },
    )

    assert page.status_code == 400
    assert "access was denied" in page.text
    assert not respx_mock.calls
