"""Tests for the publisher framework (SPEC-v2 3.10): the post status machine,
the source-rights guard, several accounts per platform and the registry
(the publish run: test_publish_run.py)."""

from itertools import product
from typing import get_args

import pytest
from clipforge import posts, social_accounts
from clipforge.models import PostStatus
from clipforge.oauth_tokens import Token
from clipforge.posts import IllegalTransition, PublishBlocked
from clipforge.publishers import registry
from clipforge.publishers.base import AccountProfile
from clipforge.token_store import TokenStore
from social_fakes import (
    ExamplePublisher,
    add_account,
    add_draft,
    clip_of,
    register_example,
    set_rights,
)
from sqlalchemy import Engine

STATUSES: tuple[PostStatus, ...] = get_args(PostStatus)
LEGAL = {
    ("draft", "queued"),
    ("draft", "canceled"),
    ("queued", "draft"),
    ("queued", "uploading"),
    ("queued", "canceled"),
    ("uploading", "published"),
    ("uploading", "failed"),
    ("uploading", "queued"),
    ("failed", "queued"),
    ("failed", "canceled"),
    ("queued", "skipped"),
    ("skipped", "queued"),
    ("skipped", "canceled"),
}


def at_status(engine: Engine, post_id: int, status: PostStatus) -> None:
    """Walk the post from draft to status along legal moves."""
    path: dict[PostStatus, list[PostStatus]] = {
        "draft": [],
        "queued": ["queued"],
        "uploading": ["queued", "uploading"],
        "published": ["queued", "uploading", "published"],
        "failed": ["queued", "uploading", "failed"],
        "canceled": ["canceled"],
        "skipped": ["queued", "skipped"],
    }
    for step in path[status]:
        posts.move(engine, post_id, step)


def test_transition_table_is_the_spec_status_machine() -> None:
    assert set(STATUSES) == set(posts.TRANSITIONS)
    moves = {(old, new) for old, new in product(STATUSES, STATUSES)}
    assert {m for m in moves if posts.can_move(*m)} == LEGAL


@pytest.mark.parametrize(("old", "new"), sorted(product(STATUSES, STATUSES)))
def test_move_applies_legal_and_rejects_illegal_transitions(
    engine: Engine, clip_id: int, old: PostStatus, new: PostStatus
) -> None:
    post_id = add_draft(engine, clip_id)
    at_status(engine, post_id, old)

    if (old, new) in LEGAL:
        assert posts.move(engine, post_id, new).status == new
    else:
        with pytest.raises(IllegalTransition) as refused:
            posts.move(engine, post_id, new)
        assert (refused.value.old, refused.value.new) == (old, new)
        assert posts.get_post(engine, post_id).status == old


def test_move_sets_only_the_allowed_fields(engine: Engine, clip_id: int) -> None:
    post_id = add_draft(engine, clip_id)
    with pytest.raises(ValueError, match="payload"):
        posts.move(engine, post_id, "queued", payload={})
    moved = posts.move(engine, post_id, "queued", error="x", attempts=2)
    assert (moved.status, moved.error, moved.attempts) == ("queued", "x", 2)


def test_new_post_is_a_draft_on_its_accounts_platform(
    engine: Engine, clip_id: int
) -> None:
    post = posts.get_post(engine, add_draft(engine, clip_id))
    assert (post.status, post.platform, post.attempts) == ("draft", "tiktok", 0)
    assert post.payload == {"title": "Bit"}
    with pytest.raises(posts.PostNotFound):
        posts.create_post(engine, clip_id=clip_id, account_id=999, payload={})
    with pytest.raises(posts.PostNotFound):
        posts.create_post(engine, clip_id=999, account_id=1, payload={})


def test_queue_is_blocked_while_source_rights_are_unset(
    engine: Engine, clip_id: int
) -> None:
    post_id = add_draft(engine, clip_id)
    set_rights(engine, clip_of(engine, clip_id).project_id, None)

    with pytest.raises(PublishBlocked) as blocked:
        posts.queue_post(engine, post_id)

    assert blocked.value.code == "source_rights_missing"
    assert posts.get_post(engine, post_id).status == "draft"
    set_rights(engine, clip_of(engine, clip_id).project_id, "permission")
    assert posts.queue_post(engine, post_id).status == "queued"


def test_platform_keeps_several_accounts_and_reconnects_in_place(
    engine: Engine, store: TokenStore
) -> None:
    def connect(external_id: str, name: str, access: str, ref: str) -> int:
        account = social_accounts.save_account(
            engine,
            store,
            "tiktok",
            AccountProfile(external_id, name, ("private only",)),
            Token(access_token=access),
            ref,
            ["video.upload"],
        )
        return account.id

    first = connect("a", "Main", "t1", "ref1")
    second = connect("b", "Second", "t2", "ref2")
    again = connect("a", "Main renamed", "t3", "ref3")

    accounts = social_accounts.list_accounts(engine, "tiktok")
    assert [(a.id, a.display_name, a.token_ref) for a in accounts] == [
        (first, "Main renamed", "ref1"),
        (second, "Second", "ref2"),
    ]
    assert again == first
    assert accounts[0].restrictions == ["private only"]
    assert accounts[0].scopes == ["video.upload"]
    assert store.load("ref1") == Token(access_token="t3")
    assert store.load("ref3") is None
    assert social_accounts.list_accounts(engine, "youtube") == []


def test_disconnect_needs_no_pending_posts_and_keeps_the_history(
    engine: Engine, clip_id: int, store: TokenStore
) -> None:
    account_id = add_account(engine)
    store.save("ref-acct-1", Token(access_token="t"))
    done = add_draft(engine, clip_id, account_id)
    at_status(engine, done, "published")
    waiting = add_draft(engine, clip_id, account_id)

    with pytest.raises(social_accounts.AccountBusy, match="1 post"):
        social_accounts.disconnect(engine, store, account_id)
    posts.move(engine, waiting, "canceled")
    social_accounts.disconnect(engine, store, account_id)

    assert social_accounts.list_accounts(engine) == []
    assert store.load("ref-acct-1") is None
    kept = posts.get_post(engine, done)
    assert (kept.status, kept.account_id) == ("published", None)
    with pytest.raises(social_accounts.AccountNotFound):
        social_accounts.disconnect(engine, store, account_id)


def test_registry_says_why_a_platform_cannot_be_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(registry, "ENTRIES", {})
    with pytest.raises(registry.PublisherUnavailable) as missing:
        registry.publisher("tiktok")
    assert (missing.value.status, missing.value.code) == (501, "not_supported")
    assert not registry.supported("tiktok")

    register_example(monkeypatch, configured=False)
    with pytest.raises(registry.PublisherUnavailable) as unset:
        registry.publisher("tiktok")
    assert (unset.value.status, unset.value.code) == (412, "needs_credentials")
    assert "EXAMPLE_CLIENT_ID" in unset.value.message
    assert (registry.supported("tiktok"), registry.configured("tiktok")) == (
        True,
        False,
    )

    register_example(monkeypatch)
    assert isinstance(registry.publisher("tiktok"), ExamplePublisher)
    assert registry.configured("tiktok")
