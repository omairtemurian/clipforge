"""Tests for the shared OAuth helper (clipforge.oauth, clipforge.oauth_tokens):
PKCE and state, the token endpoint calls and the session's
refresh. Google's token endpoint answers are recorded (respx); the clock is
fake."""

import base64
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from clipforge.oauth import (
    OAuthClient,
    OAuthError,
    OAuthSession,
    exchange_code,
    refresh,
)
from clipforge.oauth_flows import FLOW_TTL_S, PendingFlows, code_challenge
from clipforge.oauth_tokens import Token
from clipforge.token_store import TokenStore
from fake_clock import FakeClock
from gdrive_fakes import json_response

CLIENT = OAuthClient(
    name="Example",
    client_id="client-1",
    client_secret="secret-1",
    authorize_url="https://auth.example.com/authorize",
    token_url="https://auth.example.com/token",
    scopes=("read", "write"),
    authorize_params={"prompt": "consent"},
)
REDIRECT = "http://127.0.0.1:8000/api/callback"
API = "https://api.example.com/v1/me"


def form(request: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def test_code_challenge_is_the_rfc_7636_s256_example() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert code_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_code_challenge_in_hex_for_tiktok_desktop() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    challenge = code_challenge(verifier, hex_digest=True)
    assert re.fullmatch(r"[0-9a-f]{64}", challenge)
    assert bytes.fromhex(challenge) == base64.urlsafe_b64decode(
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM="
    )


def test_start_builds_the_authorization_url_with_state_and_pkce() -> None:
    flows = PendingFlows(FakeClock())
    url = flows.start(CLIENT, REDIRECT, "account-1")

    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == CLIENT.authorize_url
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert query["client_id"] == "client-1"
    assert query["redirect_uri"] == REDIRECT
    assert query["response_type"] == "code"
    assert query["scope"] == "read write"
    assert query["code_challenge_method"] == "S256"
    assert query["prompt"] == "consent"
    flow = flows.take(query["state"], "Example")
    assert re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", flow.code_verifier)
    assert query["code_challenge"] == code_challenge(flow.code_verifier)
    assert (flow.token_ref, flow.redirect_uri) == ("account-1", REDIRECT)


def test_a_state_is_taken_once_and_only_by_its_client() -> None:
    flows = PendingFlows(FakeClock())
    state = parse_qs(urlsplit(flows.start(CLIENT, REDIRECT, "a")).query)["state"][0]
    other = parse_qs(urlsplit(flows.start(CLIENT, REDIRECT, "b")).query)["state"][0]
    assert state != other

    flows.take(state, "Example")
    with pytest.raises(OAuthError) as again:
        flows.take(state, "Example")
    assert again.value.code == "invalid_state"
    with pytest.raises(OAuthError):
        flows.take(other, "Another app")
    with pytest.raises(OAuthError):
        flows.take("made-up", "Example")


def test_a_flow_expires_after_its_ttl() -> None:
    clock = FakeClock()
    flows = PendingFlows(clock)
    state = parse_qs(urlsplit(flows.start(CLIENT, REDIRECT, "a")).query)["state"][0]
    clock.now += FLOW_TTL_S + 1
    with pytest.raises(OAuthError):
        flows.take(state, "Example")


def test_start_rejects_a_token_ref_that_is_not_a_file_name() -> None:
    with pytest.raises(ValueError):
        PendingFlows().start(CLIENT, REDIRECT, "../escape")


def test_exchange_code_posts_the_verifier_and_reads_the_token(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.post(CLIENT.token_url).mock(
        return_value=json_response(200, "token_exchange")
    )
    clock = FakeClock()
    flows = PendingFlows(clock)
    state = parse_qs(urlsplit(flows.start(CLIENT, REDIRECT, "a")).query)["state"][0]
    flow = flows.take(state, "Example")

    token = exchange_code(CLIENT, flow, "4/code", clock=clock)

    assert form(route.calls.last.request) == {
        "grant_type": "authorization_code",
        "code": "4/code",
        "code_verifier": flow.code_verifier,
        "redirect_uri": REDIRECT,
        "client_id": "client-1",
        "client_secret": "secret-1",
    }
    assert token.access_token == "ya29.a0-recorded-access-token-1"
    assert token.refresh_token == "1//0g-recorded-refresh-token"
    assert token.expires_at == clock.now + 3599
    assert token.scope == "https://www.googleapis.com/auth/drive.readonly"


def test_exchange_code_without_secret_and_a_refusal(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.post(CLIENT.token_url).mock(
        return_value=httpx.Response(400, json={"error": "invalid_request"})
    )
    public = OAuthClient(**{**CLIENT.__dict__, "client_secret": ""})
    flows = PendingFlows()
    state = parse_qs(urlsplit(flows.start(public, REDIRECT, "a")).query)["state"][0]

    with pytest.raises(OAuthError) as refused:
        exchange_code(public, flows.take(state, "Example"), "4/code")

    assert refused.value.code == "token_error"
    assert "client_secret" not in form(route.calls.last.request)


def test_refresh_keeps_the_refresh_token_google_does_not_resend(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.post(CLIENT.token_url).mock(
        return_value=json_response(200, "token_refresh")
    )
    clock = FakeClock()
    old = Token(access_token="old", refresh_token="1//keep", expires_at=0)

    new = refresh(CLIENT, old, clock=clock)

    assert form(route.calls.last.request) == {
        "grant_type": "refresh_token",
        "refresh_token": "1//keep",
        "client_id": "client-1",
        "client_secret": "secret-1",
    }
    assert new.access_token == "ya29.a0-recorded-access-token-2"
    assert new.refresh_token == "1//keep"
    assert new.expires_at == clock.now + 3599


def test_a_revoked_refresh_token_or_none_needs_a_reconnect(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.post(CLIENT.token_url).mock(
        return_value=json_response(400, "invalid_grant")
    )
    with pytest.raises(OAuthError) as revoked:
        refresh(CLIENT, Token(access_token="a", refresh_token="1//gone"))
    assert revoked.value.code == "reconnect_required"
    assert "expired or revoked" in revoked.value.message
    with pytest.raises(OAuthError) as missing:
        refresh(CLIENT, Token(access_token="a"))
    assert missing.value.code == "reconnect_required"


def test_a_get_token_endpoint_and_a_refresh_grant_without_refresh_token(
    respx_mock: respx.MockRouter,
) -> None:
    meta = OAuthClient(
        **{
            **CLIENT.__dict__,
            "token_method": "GET",
            "refresh_grant": lambda t: {"grant_type": "swap", "token": t.access_token},
        }
    )
    route = respx_mock.get(CLIENT.token_url).mock(
        return_value=httpx.Response(
            200, json={"access_token": "long", "token_type": "bearer", "expires_in": 60}
        )
    )
    clock = FakeClock()

    new = refresh(meta, Token(access_token="short", scope="a,b"), clock=clock)

    request = route.calls.last.request
    assert not request.content
    assert dict(request.url.params) == {
        "grant_type": "swap",
        "token": "short",
        "client_id": "client-1",
        "client_secret": "secret-1",
    }
    assert (new.access_token, new.refresh_token, new.scope) == ("long", None, "a,b")
    assert new.expires_at == clock.now + 60


def test_meta_errors_name_the_reason_and_190_needs_a_reconnect(
    respx_mock: respx.MockRouter,
) -> None:
    meta = OAuthClient(**{**CLIENT.__dict__, "token_method": "GET"})
    expired = {"error": {"message": "Session has expired", "code": 190}}
    respx_mock.get(CLIENT.token_url).mock(
        return_value=httpx.Response(400, json=expired)
    )
    with pytest.raises(OAuthError) as refused:
        refresh(meta, Token(access_token="a", refresh_token="r"))
    assert refused.value.code == "reconnect_required"
    assert "Session has expired" in refused.value.message
    flows = PendingFlows()
    state = parse_qs(urlsplit(flows.start(meta, REDIRECT, "a")).query)["state"][0]
    with pytest.raises(OAuthError) as first:
        exchange_code(meta, flows.take(state, "Example"), "code")
    assert first.value.code == "token_error"


def test_session_refreshes_an_expired_token_before_the_request(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    clock = FakeClock()
    store = TokenStore(tmp_path / "tokens", tmp_path)
    store.save(
        "me", Token(access_token="old", refresh_token="1//r", expires_at=clock.now + 30)
    )
    respx_mock.post(CLIENT.token_url).mock(
        return_value=json_response(200, "token_refresh")
    )
    api = respx_mock.get(API).mock(return_value=httpx.Response(200, json={"ok": 1}))

    response = OAuthSession(CLIENT, store, "me", clock=clock).request("GET", API)

    assert response.json() == {"ok": 1}
    assert api.calls.last.request.headers["authorization"] == (
        "Bearer ya29.a0-recorded-access-token-2"
    )
    saved = store.load("me")
    assert saved is not None and saved.refresh_token == "1//r"


def test_session_refreshes_once_after_a_401(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    store = TokenStore(tmp_path / "tokens", tmp_path)
    store.save("me", Token(access_token="old", refresh_token="1//r"))
    refreshes = respx_mock.post(CLIENT.token_url).mock(
        return_value=json_response(200, "token_refresh")
    )
    api = respx_mock.get(API).mock(
        side_effect=[httpx.Response(401), httpx.Response(401)]
    )

    response = OAuthSession(CLIENT, store, "me").request("GET", API)

    assert response.status_code == 401
    assert refreshes.call_count == 1
    assert [c.request.headers["authorization"] for c in api.calls] == [
        "Bearer old",
        "Bearer ya29.a0-recorded-access-token-2",
    ]


def test_session_without_a_token_is_not_connected(tmp_path: Path) -> None:
    with pytest.raises(OAuthError) as missing:
        OAuthSession(
            CLIENT, TokenStore(tmp_path / "tokens", tmp_path), "me"
        ).access_token()
    assert missing.value.code == "not_connected"
