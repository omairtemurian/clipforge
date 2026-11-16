"""Tests of the autopilot's Pro Edit variants (clipforge.autopilot.proedit,
SPEC-v3 1.5, 3.8): with the campaign's switch on and allow_heavy_edits "true"
each pending draft's clip gets a Pro Edit variant; in every other case (the
switch x allow_heavy_edits matrix, Pro Edit off, a usage cap used up) none
does. The originals and their drafts stay as they are and the owner finds
both in the inbox; the autopilot never approves anything."""

import itertools
from datetime import UTC, datetime

import pytest
import respx
from autopilot_fakes import (
    add_rendered,
    finish_job,
    import_upload,
    turn_on,
    watched_campaign,
)
from clipforge import config, usage
from clipforge.autopilot import pipeline
from clipforge.autopilot import proedit as autopilot_proedit
from clipforge.autopilot.inbox import list_drafts
from clipforge.autopilot.rows import DraftRow
from clipforge.db import ClipRow
from clipforge.models import Clip, Draft, DraftStatus, HeavyEditsAllowed, ProEditRun
from clipforge.proedit.rows import ProEditRunRow
from clipforge.proedit.variants import list_variants
from fake_clock import FakeWallClock
from sqlalchemy import Engine
from sqlmodel import Session, select

NOW = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
HEAVY: list[HeavyEditsAllowed] = ["true", "false", "unknown"]


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> FakeWallClock:
    """The autopilot's clock, at NOW."""
    wall = FakeWallClock(NOW)
    monkeypatch.setattr(pipeline, "utc_now", wall)
    return wall


def prepare_upload(
    engine: Engine,
    respx_mock: respx.MockRouter,
    switch: bool,
    heavy: HeavyEditsAllowed,
) -> tuple[int, list[int]]:
    """A campaign with allow_heavy_edits heavy whose autopilot has its Pro
    Edit switch on or off, a new upload with two passing clips and a clip
    that is too long; its job not yet done. Return the project and clip
    ids (best first, the failing one last)."""
    campaign = watched_campaign(engine, allow_heavy_edits=heavy)
    turn_on(
        engine,
        campaign.id,
        proedit_enabled=switch,
        proedit_preset="skull_moment",
        proedit_max_intensity="pro",
    )
    project_id = import_upload(engine, respx_mock)
    ids = [
        add_rendered(engine, project_id, 90),
        add_rendered(engine, project_id, 70),
        add_rendered(engine, project_id, 60, start=0.0, end=75.0),
    ]
    return project_id, ids


def upload_with_clips(
    engine: Engine,
    respx_mock: respx.MockRouter,
    switch: bool,
    heavy: HeavyEditsAllowed,
) -> tuple[int, list[int]]:
    """prepare_upload with the project's job done (the drafts made)."""
    project_id, ids = prepare_upload(engine, respx_mock, switch, heavy)
    finish_job(engine, project_id)
    return project_id, ids


def inbox(engine: Engine, status: DraftStatus | None = None) -> list[Draft]:
    """The drafts of the inbox, newest first, as of NOW."""
    return list_drafts(engine, status, now=NOW)


def clips_of(engine: Engine) -> list[Clip]:
    with Session(engine) as session:
        return [row.to_model() for row in session.exec(select(ClipRow)).all()]


def runs(engine: Engine) -> list[ProEditRun]:
    with Session(engine) as session:
        return [row.to_model() for row in session.exec(select(ProEditRunRow)).all()]


@pytest.mark.parametrize(
    ("switch", "heavy"), list(itertools.product([True, False], HEAVY))
)
def test_a_variant_is_made_only_with_the_switch_on_and_heavy_edits_true(
    engine: Engine, respx_mock: respx.MockRouter, switch: bool, heavy: HeavyEditsAllowed
) -> None:
    project_id, ids = upload_with_clips(engine, respx_mock, switch, heavy)

    made = [clip for clip in clips_of(engine) if clip.variant == "pro_edit"]
    expected = switch and heavy == "true"
    assert len(made) == (2 if expected else 0)
    assert len(runs(engine)) == len(made)
    assert [d.status for d in inbox(engine)] == ["needs_fix", "pending", "pending"]
    assert all(clip.project_id == project_id for clip in made)
    assert len(clips_of(engine)) == len(ids) + len(made)


def test_the_variants_of_the_pending_drafts_use_the_autopilots_choices(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    _, (best, second, too_long) = upload_with_clips(engine, respx_mock, True, "true")

    for original in (best, second):
        (variant,) = list_variants(engine, original)
        assert variant.parent_clip_id == original
        assert variant.status == "rendering"
    assert list_variants(engine, too_long) == []
    assert {
        (r.options.preset, r.options.intensity) for r in runs(engine) if r.options
    } == {("skull_moment", "pro")}
    assert {r.mode for r in runs(engine)} == {"start"}
    assert {r.status for r in runs(engine)} == {"queued"}


def test_the_originals_stay_as_they_were_and_nothing_is_approved(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    project_id, ids = prepare_upload(engine, respx_mock, True, "true")
    before = {c.id: c.model_dump() for c in clips_of(engine)}

    finish_job(engine, project_id)

    after = {c.id: c.model_dump() for c in clips_of(engine) if c.id in before}
    assert after == before
    assert len(clips_of(engine)) == len(ids) + 2
    with Session(engine) as session:
        rows = session.exec(select(DraftRow)).all()
    assert {row.status for row in rows} == {"pending", "needs_fix"}
    assert all(row.decided_at is None for row in rows)


def test_both_variants_are_in_the_inbox_and_none_has_a_draft_until_approved(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    _, (best, second, _) = upload_with_clips(engine, respx_mock, True, "true")

    drafts = inbox(engine, "pending")
    assert {d.clip_id for d in drafts} == {best, second}
    for draft in drafts:
        (variant,) = list_variants(engine, draft.clip_id)
        assert variant.id not in {d.clip_id for d in inbox(engine)}
    assert len(clips_of(engine)) == 5


def test_a_pro_edit_variant_of_a_draft_is_not_made_twice(
    engine: Engine, respx_mock: respx.MockRouter
) -> None:
    project_id, _ = upload_with_clips(engine, respx_mock, True, "true")
    before = len(runs(engine))

    assert pipeline.make_drafts(engine, project_id) == []

    assert len(runs(engine)) == before


def test_no_variants_with_pro_edit_turned_off_in_the_settings(
    engine: Engine,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config.settings.proedit, "enabled", False)

    upload_with_clips(engine, respx_mock, True, "true")

    assert runs(engine) == []
    assert len(inbox(engine, "pending")) == 2


def test_no_variants_while_a_usage_cap_is_used_up(
    engine: Engine,
    respx_mock: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def capped(_engine: Engine) -> None:
        raise usage.UsageCapExceeded("cap used up")

    project_id, _ = prepare_upload(engine, respx_mock, True, "true")
    monkeypatch.setattr(usage, "check_caps", capped)

    finish_job(engine, project_id)

    assert runs(engine) == []
    assert len(inbox(engine, "pending")) == 2


def test_a_variant_that_cannot_be_made_does_not_stop_the_others(
    engine: Engine, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    from clipforge.proedit import runs as proedit_runs

    real = proedit_runs.start_run
    calls: list[int] = []

    def flaky(eng: Engine, clip_id: int, options: object) -> object:
        calls.append(clip_id)
        if len(calls) == 1:
            raise RuntimeError("disk full")
        return real(eng, clip_id, options)  # type: ignore[arg-type]

    monkeypatch.setattr(proedit_runs, "start_run", flaky)

    upload_with_clips(engine, respx_mock, True, "true")

    assert len(calls) == 2
    assert len(runs(engine)) == 1
    assert len(inbox(engine, "pending")) == 2


def test_wants_variants_needs_the_switch_and_heavy_edits_true(
    engine: Engine,
) -> None:
    campaign = watched_campaign(engine)
    on = turn_on(engine, campaign.id, proedit_enabled=True)
    off = turn_on(engine, campaign.id, proedit_enabled=False)
    allowed = campaign.model_copy(update={"allow_heavy_edits": "true"})

    assert campaign.allow_heavy_edits == "unknown"
    assert not autopilot_proedit.wants_variants(campaign, on)
    assert autopilot_proedit.wants_variants(allowed, on)
    assert not autopilot_proedit.wants_variants(allowed, off)
