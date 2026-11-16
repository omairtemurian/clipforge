"""The in-app notifications (SPEC-v2 3.17): what makes one (a finished
project, a failed render, a published or failed post, a monthly cap nearly
or fully used), that each goes to the email channel when SMTP is set, that
a quota warning comes once a month, and the read/delete bookkeeping."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from clipforge import clips, config, jobs, notifications, posts, usage
from clipforge.asset_rows import UsageRecordRow
from clipforge.models import ProcessingSettings
from clipforge.pipeline.render import RenderError
from fakes import FIXTURES, FakeLLMClient
from post_api_fakes import accounts, rendered_clip
from seed import add_clip, add_project
from smtp_fakes import Mailbox, smtp_server
from sqlalchemy import Engine
from sqlmodel import Session

NOW = datetime(2030, 1, 15, 9, 0, tzinfo=UTC)


def titles(engine: Engine) -> list[str]:
    return [n.title for n in notifications.list_notifications(engine).items]


def finish_post(engine: Engine, status: str, **ended: Any) -> None:
    clip_id = rendered_clip(engine, "Pizza night")
    (account,) = accounts(engine, "tiktok")
    post = posts.create_post(
        engine, clip_id=clip_id, account_id=account, payload={}, scheduled_at=NOW
    )
    posts.queue_post(engine, post.id, NOW)
    posts.move(engine, post.id, "uploading", attempts=1, attempted_at=NOW)
    posts.move(engine, post.id, status, **ended)  # type: ignore[arg-type]


def test_a_published_post_notifies_with_its_link(engine: Engine) -> None:
    finish_post(
        engine, "published", url="https://tiktok.com/@a/1", external_post_id="1"
    )

    (note,) = notifications.list_notifications(engine).items
    assert (note.kind, note.title) == (
        "post_published",
        "Posted to tiktok: Pizza night",
    )
    assert note.body == "https://tiktok.com/@a/1"
    assert note.link == "/post-history"


def test_a_failed_post_notifies_with_its_error(engine: Engine) -> None:
    finish_post(engine, "failed", error="Too big")

    (note,) = notifications.list_notifications(engine).items
    assert (note.kind, note.body) == ("post_failed", "Too big")
    assert note.title == "Post to tiktok failed: Pizza night"


def test_a_post_that_is_not_finished_says_nothing(engine: Engine) -> None:
    clip_id = rendered_clip(engine)
    (account,) = accounts(engine, "tiktok")
    post = posts.create_post(engine, clip_id=clip_id, account_id=account, payload={})
    posts.queue_post(engine, post.id, NOW)

    notifications.posts_finished(engine, [post.id, 999])

    assert titles(engine) == []


def test_an_interrupted_upload_notifies_as_a_failed_post(engine: Engine) -> None:
    from clipforge.scheduler import post_queue

    clip_id = rendered_clip(engine)
    (account,) = accounts(engine, "tiktok")
    post = posts.create_post(engine, clip_id=clip_id, account_id=account, payload={})
    posts.queue_post(engine, post.id, NOW)
    posts.move(engine, post.id, "uploading", attempts=1, attempted_at=NOW)

    assert post_queue.fail_interrupted(engine) == [post.id]

    (note,) = notifications.list_notifications(engine).items
    assert note.kind == "post_failed"


def test_a_failed_render_notifies_with_the_clip_link(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id = add_project(engine)
    clip_id = add_clip(engine, project_id, "candidate", 70, "Bit")
    work = tmp_path / "work"
    work.mkdir()

    def fails(*_: object, **__: object) -> None:
        raise RenderError("ffmpeg exited 1")

    monkeypatch.setattr(clips, "prepare_render", lambda *_, **__: object())
    monkeypatch.setattr(clips, "run_render", fails)

    assert clips.render_clip_row(engine, clip_id, work).status == "failed"

    (note,) = notifications.list_notifications(engine).items
    assert (note.kind, note.title, note.link) == (
        "render_failed",
        "Render failed: Bit",
        f"/clips/{clip_id}",
    )


def test_a_rendered_clip_makes_no_notification(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clip_id = add_clip(engine, add_project(engine), "candidate", 70, "Bit")
    monkeypatch.setattr(clips, "prepare_render", lambda *_, **__: object())
    monkeypatch.setattr(clips, "run_render", lambda *_, **__: None)
    monkeypatch.setattr(clips, "write_srt", lambda *_, **__: None)
    monkeypatch.setattr(clips, "write_metadata", lambda *_, **__: None)

    assert clips.render_clip_row(engine, clip_id, tmp_path).status == "rendered"

    assert titles(engine) == []


@pytest.mark.slow
@pytest.mark.usefixtures("yamnet_cfg", "face_cfg")
def test_a_processed_video_notifies_that_it_is_ready(
    engine: Engine, sample_mp4: Path
) -> None:
    jobs.enqueue_process(engine, str(sample_mp4), ProcessingSettings(num_clips=1))

    assert jobs.run_next(
        engine, llm=FakeLLMClient(), transcript=FIXTURES / "transcript.json"
    )

    (note,) = notifications.list_notifications(engine).items
    assert note.kind == "project_done"
    assert note.title == "ClipForge sample fixture is ready"
    assert note.body.startswith("1 clip found.")
    assert note.link == "/projects/1"


def test_a_project_that_is_gone_says_nothing(engine: Engine) -> None:
    notifications.project_done(engine, 404)
    notifications.render_failed(engine, 404)

    assert titles(engine) == []


def add_usage(engine: Engine, kind: str, units: float, at: datetime = NOW) -> None:
    with Session(engine) as session:
        session.add(UsageRecordRow(kind=kind, units=units, at=at))
        session.commit()


def cap(monkeypatch: pytest.MonkeyPatch, **changes: Any) -> None:
    monkeypatch.setattr(config, "settings", config.settings.model_copy(update=changes))


def test_quota_warnings_need_a_cap(engine: Engine) -> None:
    add_usage(engine, usage.LLM_TOKENS, 10**9)

    notifications.quota_warnings(engine, NOW)

    assert titles(engine) == []


def test_a_cap_warns_at_80_percent_then_when_used_up_once_each(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    cap(monkeypatch, usage_cap_llm_tokens=1000)
    add_usage(engine, usage.LLM_TOKENS, 700)
    notifications.quota_warnings(engine, NOW)
    assert titles(engine) == []

    add_usage(engine, usage.LLM_TOKENS, 100)
    notifications.quota_warnings(engine, NOW)
    notifications.quota_warnings(engine, NOW)
    (warning,) = notifications.list_notifications(engine).items
    assert warning.kind == "quota_warning"
    assert warning.title == "Monthly cap nearly used up"
    assert warning.body.startswith("800 LLM tokens of 1,000 LLM tokens in 2030-01.")
    assert warning.link == "/settings"

    add_usage(engine, usage.LLM_TOKENS, 300)
    notifications.quota_warnings(engine, NOW)
    notifications.quota_warnings(engine, NOW)
    assert titles(engine) == ["Monthly cap used up", "Monthly cap nearly used up"]


def test_the_warning_comes_again_the_next_month_and_follows_the_percent(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    cap(monkeypatch, usage_cap_api_calls=100, quota_warn_percent=50.0)
    add_usage(engine, usage.API_CALLS, 60)
    add_usage(engine, usage.API_CALLS, 55, datetime(2030, 2, 3, tzinfo=UTC))

    notifications.quota_warnings(engine, NOW)
    notifications.quota_warnings(engine, datetime(2030, 2, 4, tzinfo=UTC))

    assert len(notifications.list_notifications(engine).items) == 2


def test_a_job_that_ends_warns_of_a_cap_its_compute_used(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cap(monkeypatch, usage_cap_compute_hours=0.0001)
    add_usage(engine, usage.COMPUTE, 0.5, datetime.now(UTC))
    jobs.enqueue_process(engine, str(tmp_path / "missing.mp4"), ProcessingSettings())

    jobs.run_next(engine)

    assert "Monthly cap used up" in titles(engine)


def test_a_notification_is_emailed_when_smtp_is_set(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with smtp_server() as (port, box):
        cap(
            monkeypatch,
            smtp_host="127.0.0.1",
            smtp_port=port,
            smtp_from="cf@example.com",
        )
        finish_post(engine, "failed", error="Too big")
    assert_one_mail(box, "[ClipForge] Post to tiktok failed: Pizza night")


def assert_one_mail(box: Mailbox, subject: str) -> None:
    (message,) = box.messages
    assert message["Subject"] == subject
    assert str(message.get_payload()).strip() == "Too big"


def test_notifications_are_not_emailed_without_smtp_host(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with smtp_server() as (port, box):
        cap(monkeypatch, smtp_host="", smtp_port=port, smtp_from="cf@example.com")
        finish_post(engine, "failed", error="Too big")

    assert box.messages == []
    assert len(notifications.list_notifications(engine).items) == 1


def test_an_unreachable_mail_server_does_not_stop_the_post(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    with smtp_server() as (port, _):
        pass
    cap(monkeypatch, smtp_host="127.0.0.1", smtp_port=port, smtp_from="a@example.com")

    finish_post(engine, "failed", error="Too big")

    assert posts.get_post(engine, 1).status == "failed"
    assert len(notifications.list_notifications(engine).items) == 1


def test_read_unread_and_delete(engine: Engine) -> None:
    first = notifications.notify(engine, "test", "One")
    second = notifications.notify(engine, "test", "Two", "body", "/x")
    assert first is not None and second is not None

    listed = notifications.list_notifications(engine)
    assert [n.title for n in listed.items] == ["Two", "One"]
    assert listed.unread_count == 2

    read = notifications.mark_read(engine, first.id)
    assert read.read_at is not None
    assert notifications.mark_read(engine, first.id).read_at == read.read_at
    unread = notifications.list_notifications(engine, unread_only=True)
    assert [n.title for n in unread.items] == ["Two"]
    assert unread.unread_count == 1

    assert notifications.mark_all_read(engine) == 1
    assert notifications.list_notifications(engine).unread_count == 0

    notifications.delete(engine, first.id)
    assert titles(engine) == ["Two"]
    with pytest.raises(notifications.NotificationNotFound):
        notifications.delete(engine, first.id)
    with pytest.raises(notifications.NotificationNotFound):
        notifications.mark_read(engine, first.id)


def test_a_long_message_is_cut_and_the_list_has_a_limit(engine: Engine) -> None:
    note = notifications.notify(engine, "test", "T" * 500, "b" * 5000)
    assert note is not None
    assert len(note.title) == 200 and note.title.endswith("…")
    assert len(note.body) == 1000
    for index in range(3):
        notifications.notify(engine, "test", f"n{index}")

    assert len(notifications.list_notifications(engine, limit=2).items) == 2
    assert len(notifications.list_notifications(engine, limit=0).items) == 1


def test_the_same_dedupe_key_is_one_notification(engine: Engine) -> None:
    assert notifications.notify(engine, "test", "A", dedupe_key="k") is not None
    assert notifications.notify(engine, "test", "B", dedupe_key="k") is None

    assert titles(engine) == ["A"]
