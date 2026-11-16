"""Tests for connecting a YouTube channel through the account endpoints
(clipforge.api.accounts with the YouTube publisher): the Google OAuth app
it needs, the authorize URL (upload + read-only scopes, account chooser)
and the callback that names the channel from channels.list (respx), plus
the 409 answer of a blocked publish."""

from urllib.parse import parse_qs, urlsplit

import httpx
import respx
from apihelpers import assert_error
from clipforge.posts import PublishBlocked
from clipforge.publishers import youtube
from clipforge.sources.gdrive import TOKEN_URL
from fastapi.testclient import TestClient
from gdrive_fakes import CLIENT_ID, configure_google
from pytest import MonkeyPatch
from youtube_publish_fakes import ACCESS, CHANNEL_ID, REFRESH, answer

CALLBACK = "http://testserver/api/accounts/youtube/callback"


def test_youtube_needs_the_google_oauth_app(
    client: TestClient, monkeypatch: MonkeyPatch
) -> None:
    configure_google(monkeypatch, "")
    statuses = {s["platform"]: s for s in client.get("/api/accounts/platforms").json()}
    assert (statuses["youtube"]["supported"], statuses["youtube"]["configured"]) == (
        True,
        False,
    )

    message = assert_error(
        client.post("/api/accounts/youtube/connect"), 412, "needs_credentials"
    )

    assert "GOOGLE_OAUTH_CLIENT_ID" in message
    assert "GOOGLE_OAUTH_CLIENT_SECRET" in message


def test_a_channel_is_connected_with_its_restrictions(
    client: TestClient, monkeypatch: MonkeyPatch, respx_mock: respx.MockRouter
) -> None:
    configure_google(monkeypatch)
    token = respx_mock.post(TOKEN_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": ACCESS,
                "refresh_token": REFRESH,
                "expires_in": 3599,
                "scope": f"{youtube.UPLOAD_SCOPE} {youtube.READONLY_SCOPE}",
                "token_type": "Bearer",
            },
        )
    )
    respx_mock.get(youtube.CHANNELS_URL).mock(return_value=answer(200, "channels_mine"))

    assert client.get("/api/accounts/platforms").json()[0] == {
        "platform": "youtube",
        "supported": True,
        "configured": True,
        "settings_keys": ["GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"],
    }
    url = client.post("/api/accounts/youtube/connect").json()["authorize_url"]
    query = parse_qs(urlsplit(url).query)
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert query["client_id"] == [CLIENT_ID]
    assert query["redirect_uri"] == [CALLBACK]
    assert query["scope"] == [f"{youtube.UPLOAD_SCOPE} {youtube.READONLY_SCOPE}"]
    assert query["prompt"] == ["select_account"]
    page = client.get(
        "/api/accounts/youtube/callback",
        params={"state": query["state"][0], "code": "4/0Ab-code"},
    )

    assert page.status_code == 200
    assert "Clip Lab is connected" in page.text
    assert token.called
    [account] = client.get("/api/accounts", params={"platform": "youtube"}).json()
    assert (account["external_id"], account["display_name"]) == (
        CHANNEL_ID,
        "Clip Lab",
    )
    assert account["restrictions"][1] == youtube.UNAUDITED
    usage = client.get("/api/usage").json()
    assert "youtube_quota_units" in str(usage)


def test_a_blocked_publish_answers_409(client: TestClient) -> None:
    def blocked() -> None:
        raise PublishBlocked("source_rights_missing", "Set the source rights.")

    client.app.router.add_api_route("/api/test-blocked", blocked)  # type: ignore[attr-defined]

    message = assert_error(
        client.get("/api/test-blocked"), 409, "source_rights_missing"
    )
    assert message == "Set the source rights."
