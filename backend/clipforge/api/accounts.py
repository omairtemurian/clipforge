"""Social account endpoints (SPEC-v2 3.10): connect accounts with each
platform's OAuth sign-in (several per platform), list and disconnect them.

    GET    /accounts                       -> list[SocialAccount]
    GET    /accounts/platforms             -> list[PlatformStatus]
    POST   /accounts/{platform}/connect    -> AccountConnect (the sign-in URL)
    GET    /accounts/{platform}/callback   <- the platform's redirect; HTML
    PUT    /accounts/{account_id}/default  -> SocialAccount (its platform's default)
    PUT    /accounts/{account_id}/hashtags -> SocialAccount (its always_hashtags)
    DELETE /accounts/{account_id}          -> 204 (forgets the token too)

connect answers 501 not_supported for a platform without a publisher and
412 needs_credentials while its OAuth app is not configured. The callback
stores the token in the encrypted token store (never in a row or a log).
"""

import logging
from typing import Annotated, get_args

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import Engine

from clipforge import social_accounts, usage
from clipforge.api.deps import get_engine
from clipforge.api.errors import ApiError, not_found
from clipforge.api.oauth_pages import result_page
from clipforge.models import AccountHashtags, SocialAccount, SocialPlatform
from clipforge.oauth import OAuthError, exchange_code
from clipforge.oauth_flows import pending
from clipforge.oauth_tokens import new_token_ref
from clipforge.publishers import registry
from clipforge.publishers.base import Publisher, PublishError
from clipforge.token_store import TokenStore

logger = logging.getLogger(__name__)

router = APIRouter()

CALLBACK_ROUTE = "accounts_callback"


class PlatformStatus(BaseModel):
    """Whether ClipForge can publish to a platform (supported) and whether
    the owner's developer app for it is set (configured); settings_keys name
    the settings (env vars) that hold the app's keys."""

    platform: SocialPlatform
    supported: bool
    configured: bool
    settings_keys: list[str]


class AccountConnect(BaseModel):
    """The platform's sign-in page that connects an account."""

    authorize_url: str


@router.get("/accounts")
def list_accounts(
    engine: Annotated[Engine, Depends(get_engine)],
    platform: SocialPlatform | None = None,
) -> list[SocialAccount]:
    """Return the connected accounts (of platform, if given)."""
    return social_accounts.list_accounts(engine, platform)


@router.get("/accounts/platforms")
def list_platforms() -> list[PlatformStatus]:
    """Return every platform with whether it can be used."""
    platforms: tuple[SocialPlatform, ...] = get_args(SocialPlatform)
    return [
        PlatformStatus(
            platform=platform,
            supported=registry.supported(platform),
            configured=registry.configured(platform),
            settings_keys=registry.settings_keys(platform),
        )
        for platform in platforms
    ]


@router.post("/accounts/{platform}/connect")
def connect_account(platform: SocialPlatform, request: Request) -> AccountConnect:
    """Start a sign-in whose redirect comes back to the callback; the
    account it connects gets a new token_ref (or keeps its own)."""
    publisher = _publisher(platform)
    redirect_uri = str(request.url_for(CALLBACK_ROUTE, platform=platform))
    url = pending.start(publisher.client, redirect_uri, new_token_ref())
    return AccountConnect(authorize_url=url)


@router.get(
    "/accounts/{platform}/callback",
    name=CALLBACK_ROUTE,
    response_class=HTMLResponse,
)
def account_callback(
    platform: SocialPlatform,
    engine: Annotated[Engine, Depends(get_engine)],
    state: str = "",
    code: str = "",
    error: str = "",
) -> HTMLResponse:
    """Finish the sign-in: trade the code for a token, ask the platform who
    signed in and save the account. Answers a page that tells the user to go
    back to ClipForge (400 on failure)."""
    try:
        publisher = _publisher(platform)
        client = publisher.client
        flow = pending.take(state, client.name)
        if error or not code:
            reason = "access was denied" if error == "access_denied" else error
            raise OAuthError(
                "authorization_denied",
                f"No {client.name} account was connected: "
                f"{reason or 'no code was sent'}.",
            )
        token = exchange_code(client, flow, code, transport=publisher.transport)
        with usage.recording(engine, None):
            token = publisher.finish_sign_in(token)
            profile = publisher.fetch_account(token)
        account = social_accounts.save_account(
            engine,
            TokenStore.from_settings(),
            platform,
            profile,
            token,
            flow.token_ref,
            client.granted(token.scope) or list(client.scopes),
        )
    except (OAuthError, PublishError, ApiError) as exc:
        logger.info("%s sign-in failed: %s", platform, type(exc).__name__)
        return result_page("No account was connected", str(exc), 400)
    return result_page(
        f"{client.name} account connected",
        f"{account.display_name} is connected. You can close this tab and go "
        "back to ClipForge.",
        200,
    )


@router.put("/accounts/{account_id}/default")
def make_default(
    account_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> SocialAccount:
    """Make the account the one that a one-click post uses on its platform
    (the platform's other accounts stop being it)."""
    try:
        return social_accounts.set_default(engine, account_id)
    except social_accounts.AccountNotFound as exc:
        raise not_found("account", account_id) from exc


@router.put("/accounts/{account_id}/hashtags")
def set_hashtags(
    account_id: int,
    body: AccountHashtags,
    engine: Annotated[Engine, Depends(get_engine)],
) -> SocialAccount:
    """Set the hashtags that every generated post to the account carries."""
    try:
        return social_accounts.set_always_hashtags(
            engine, account_id, body.always_hashtags
        )
    except social_accounts.AccountNotFound as exc:
        raise not_found("account", account_id) from exc


@router.delete("/accounts/{account_id}", status_code=204)
def disconnect_account(
    account_id: int, engine: Annotated[Engine, Depends(get_engine)]
) -> Response:
    """Forget the account and its token on this machine; 409 account_busy
    while it has posts waiting to be published."""
    try:
        social_accounts.disconnect(engine, TokenStore.from_settings(), account_id)
    except social_accounts.AccountNotFound as exc:
        raise not_found("account", account_id) from exc
    except social_accounts.AccountBusy as exc:
        raise ApiError(409, "account_busy", str(exc)) from exc
    return Response(status_code=204)


def _publisher(platform: SocialPlatform) -> Publisher:
    """Return platform's publisher as ApiErrors (501, 412)."""
    try:
        return registry.publisher(platform)
    except registry.PublisherUnavailable as exc:
        raise ApiError(exc.status, exc.code, exc.message) from exc
