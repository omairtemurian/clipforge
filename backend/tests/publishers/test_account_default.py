"""Tests of the default account of each platform (one-click quick post):
the first account connected is the default, it can be moved, a default that
is disconnected passes to the oldest account left, and the avatar the
platform gave is kept (https only)."""

import pytest
from clipforge import social_accounts
from clipforge.oauth_tokens import Token
from clipforge.publishers.base import AccountProfile
from clipforge.token_store import TokenStore
from sqlalchemy import Engine


def connect(
    engine: Engine, store: TokenStore, external_id: str, **profile: str | None
) -> int:
    account = social_accounts.save_account(
        engine,
        store,
        "tiktok",
        AccountProfile(external_id, external_id.title(), **profile),  # type: ignore[arg-type]
        Token(access_token="t"),
        f"ref-{external_id}",
        [],
    )
    return account.id


def defaults(engine: Engine) -> list[str]:
    return [
        a.external_id for a in social_accounts.list_accounts(engine) if a.is_default
    ]


def test_the_first_account_of_a_platform_is_its_default(
    engine: Engine, store: TokenStore
) -> None:
    first = connect(engine, store, "a")
    connect(engine, store, "b")
    connect(engine, store, "a")

    default = social_accounts.default_account(engine, "tiktok")

    assert default is not None and default.id == first
    assert defaults(engine) == ["a"]
    assert social_accounts.default_account(engine, "youtube") is None


def test_another_account_can_become_the_default(
    engine: Engine, store: TokenStore
) -> None:
    connect(engine, store, "a")
    second = connect(engine, store, "b")

    chosen = social_accounts.set_default(engine, second)

    assert chosen.is_default
    assert defaults(engine) == ["b"]
    with pytest.raises(social_accounts.AccountNotFound):
        social_accounts.set_default(engine, 99)


def test_a_disconnected_default_passes_to_the_oldest_account(
    engine: Engine, store: TokenStore
) -> None:
    first = connect(engine, store, "a")
    connect(engine, store, "b")
    connect(engine, store, "c")

    social_accounts.disconnect(engine, store, first)

    assert defaults(engine) == ["b"]
    social_accounts.disconnect(
        engine, store, social_accounts.list_accounts(engine)[1].id
    )
    assert defaults(engine) == ["b"]


def test_only_an_https_avatar_is_kept(engine: Engine, store: TokenStore) -> None:
    connect(engine, store, "a", avatar_url="https://cdn.example.com/a.jpg")
    connect(engine, store, "b", avatar_url="javascript:alert(1)")

    avatars = [a.avatar_url for a in social_accounts.list_accounts(engine)]

    assert avatars == ["https://cdn.example.com/a.jpg", None]
