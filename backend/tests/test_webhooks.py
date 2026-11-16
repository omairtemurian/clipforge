"""Tests of the webhooks (clipforge.webhooks, webhook_events): the secret
kept encrypted, which events reach which webhooks, and the events that jobs
and posts raise."""

import pytest
from clipforge import posts, process, webhook_events, webhooks
from clipforge.models import ProcessingSettings, WebhookCreate, WebhookUpdate
from clipforge.scheduler import post_queue
from clipforge.webhook_rows import WebhookRow
from post_api_fakes import accounts, rendered_clip
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session
from webhook_fakes import URL, delivery_log, register


def queued_post(engine: Engine) -> int:
    clip_id = rendered_clip(engine)
    (account_id,) = accounts(engine, "tiktok")
    draft = posts.create_post(
        engine, clip_id=clip_id, account_id=account_id, payload={}
    )
    return posts.queue_post(engine, draft.id).id


def test_the_secret_is_shown_once_and_stored_encrypted(engine: Engine, rows) -> None:  # type: ignore[no-untyped-def]
    created = register(engine)

    assert created.secret.startswith("whsec_") and len(created.secret) == 49
    assert register(engine).secret != created.secret
    (stored,) = rows("SELECT secret_enc FROM webhook WHERE id = 1")
    assert created.secret not in stored[0]
    with Session(engine) as session:
        row = session.get(WebhookRow, created.id)
        assert row is not None
        assert webhooks.secret_of(row) == created.secret
    listed = webhooks.get_webhook(engine, created.id)
    assert "secret" not in listed.model_dump()
    assert webhooks.list_webhooks(engine)[0] == listed


@pytest.mark.parametrize(
    "url", ["", "ftp://x.test/a", "hooks.example.test", "https://", "javascript:1"]
)
def test_only_http_addresses_are_webhook_urls(url: str) -> None:
    with pytest.raises(ValidationError, match="http"):
        WebhookCreate(url=url, events=["clip.rendered"])


def test_events_must_be_known_and_are_kept_once_in_order() -> None:
    body = WebhookCreate(
        url=URL, events=["post.failed", "clip.rendered", "post.failed"]
    )

    assert body.events == ["clip.rendered", "post.failed"]
    with pytest.raises(ValidationError):
        WebhookCreate(url=URL, events=[])
    with pytest.raises(ValidationError):
        WebhookCreate(url=URL, events=["project.deleted"])  # type: ignore[list-item]


def test_an_event_goes_to_the_enabled_webhooks_that_want_it(engine: Engine) -> None:
    wants = register(engine, ["clip.rendered", "post.failed"])
    other = register(engine, ["post.published"])
    paused = register(engine, ["clip.rendered"])
    webhooks.update_webhook(engine, paused.id, WebhookUpdate(enabled=False))

    ids = webhooks.emit(engine, "clip.rendered", {"clip": {"id": 7}})

    assert len(ids) == 1
    (delivery,) = delivery_log(engine, wants.id)
    assert (delivery.id, delivery.event, delivery.data) == (
        ids[0],
        "clip.rendered",
        {"clip": {"id": 7}},
    )
    assert (delivery.status, delivery.attempts) == ("pending", 0)
    assert delivery.next_attempt_at == delivery.created_at
    assert delivery_log(engine, other.id) == []
    assert delivery_log(engine, paused.id) == []


def test_update_changes_only_the_fields_given(engine: Engine) -> None:
    hook = register(engine, ["clip.rendered"])

    changed = webhooks.update_webhook(
        engine, hook.id, WebhookUpdate(url="https://b.test/x", events=["post.failed"])
    )

    assert (changed.url, changed.events, changed.enabled) == (
        "https://b.test/x",
        ["post.failed"],
        True,
    )
    assert changed.created_at == hook.created_at
    with Session(engine) as session:
        row = session.get(WebhookRow, hook.id)
        assert row is not None and webhooks.secret_of(row) == hook.secret


def test_deleting_a_webhook_deletes_its_log(engine: Engine, rows) -> None:  # type: ignore[no-untyped-def]
    hook = register(engine)
    webhooks.emit(engine, "post.failed", {})

    webhooks.delete_webhook(engine, hook.id)

    assert rows("SELECT * FROM webhook_delivery") == []
    for call in (
        lambda: webhooks.get_webhook(engine, hook.id),
        lambda: webhooks.delete_webhook(engine, hook.id),
        lambda: webhooks.list_deliveries(engine, hook.id),
        lambda: webhooks.update_webhook(engine, hook.id, WebhookUpdate()),
    ):
        with pytest.raises(webhooks.WebhookNotFound):
            call()


def test_emit_never_raises(blank_engine: Engine) -> None:
    assert webhooks.emit(blank_engine, "clip.rendered", {}) == []


def test_a_published_post_raises_post_published(engine: Engine) -> None:
    hook = register(engine)
    post_id = queued_post(engine)
    posts.move(engine, post_id, "uploading")

    posts.move(engine, post_id, "published", external_post_id="v1", url="https://ex/v1")

    (delivery,) = delivery_log(engine, hook.id)
    assert delivery.event == "post.published"
    (clip_id,) = [posts.get_post(engine, post_id).clip_id]
    assert delivery.data == {
        "post": {
            "id": post_id,
            "clip_id": clip_id,
            "platform": "tiktok",
            "status": "published",
            "url": "https://ex/v1",
            "external_post_id": "v1",
            "error": None,
            "attempts": 0,
        }
    }


def test_a_failed_post_raises_post_failed_but_a_retry_does_not(
    engine: Engine,
) -> None:
    hook = register(engine, ["post.failed"])
    post_id = queued_post(engine)
    posts.move(engine, post_id, "uploading")
    posts.move(engine, post_id, "queued", error="busy")
    assert delivery_log(engine, hook.id) == []

    posts.move(engine, post_id, "uploading")
    posts.move(engine, post_id, "failed", error="Video too long")

    (delivery,) = delivery_log(engine, hook.id)
    assert delivery.event == "post.failed"
    assert delivery.data["post"]["error"] == "Video too long"


def test_an_upload_that_a_stop_cut_off_raises_post_failed(engine: Engine) -> None:
    hook = register(engine, ["post.failed"])
    post_id = queued_post(engine)
    posts.move(engine, post_id, "uploading")

    assert post_queue.fail_interrupted(engine) == [post_id]

    (delivery,) = delivery_log(engine, hook.id)
    assert delivery.data["post"]["id"] == post_id
    assert delivery.data["post"]["error"] == post_queue.INTERRUPTED


def test_a_rendered_clip_raises_clip_rendered(engine: Engine) -> None:
    hook = register(engine)
    clip_id = rendered_clip(engine, "Pizza night")

    webhook_events.clip_rendered(engine, clip_id)
    webhook_events.clip_rendered(engine, 9999)

    (delivery,) = delivery_log(engine, hook.id)
    clip = delivery.data["clip"]
    assert delivery.event == "clip.rendered"
    assert (clip["id"], clip["title"]) == (clip_id, "Pizza night")
    assert clip["download_path"] == f"/api/clips/{clip_id}/download"
    assert "output_path" not in clip


def test_a_finished_process_job_raises_project_completed(
    engine: Engine, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    hook = register(engine)
    job_id = process.create_job(engine, str(tmp_path / "v.mp4"), ProcessingSettings())

    process._finish(engine, job_id, "failed", error="boom")
    assert delivery_log(engine, hook.id) == []
    process._finish(engine, job_id, "done")

    (delivery,) = delivery_log(engine, hook.id)
    assert delivery.event == "project.completed"
    project = delivery.data["project"]
    assert project["path"] == f"/api/projects/{project['id']}"
    assert delivery.data["clips"] == []
