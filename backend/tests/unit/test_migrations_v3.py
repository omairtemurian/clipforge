"""Tests for migration 039_proedit (SPEC-v3 6): the clip variant columns, the
Pro Edit tables, the audio columns of the assets, the campaign's heavy-edits
switch and the autopilot's Pro Edit settings; and the models that show them."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from clipforge import campaigns
from clipforge.asset_rows import AssetRow
from clipforge.autopilot.settings import get_settings, save_settings
from clipforge.db import ClipRow, migrate
from clipforge.models import (
    AutopilotSettingsUpdate,
    CampaignCreate,
    CampaignPatch,
    Clip,
    CriticRound,
    CriticScore,
    EdlItem,
    ProEditPlan,
    ProEditRun,
    StyleRecipe,
    StyleReference,
)
from clipforge.proedit.rows import (
    EdlItemRow,
    ProEditPlanRow,
    ProEditRunRow,
    StyleRecipeRow,
    StyleReferenceRow,
)
from pydantic import ValidationError
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from submission_fakes import new_campaign
from v1db import migrate_to_v1, migrations_through, seed_v1

Rows = Callable[[str], list[tuple[Any, ...]]]
NOW = datetime(2030, 1, 15, 9, 0, tzinfo=UTC)
ITEM: dict[str, Any] = {
    "id": 1,
    "t_start": 1.0,
    "t_end": 1.5,
    "kind": "zoom_punch",
    "params": {"scale": 1.2},
    "reason": "Emphasis word",
}


def _columns(rows: Rows, table: str) -> list[str]:
    return [row[1] for row in rows(f"SELECT * FROM pragma_table_info('{table}')")]


def _v2_database(engine: Engine, rows: Rows, tmp_path: Path) -> None:
    """A database at migration 38 with v1 clips, a campaign with autopilot
    settings, a draft and an audio asset."""
    migrate_to_v1(engine, tmp_path)
    seed_v1(engine)
    migrate(engine, migrations_through(tmp_path, 38))
    clip_id = rows("SELECT id FROM clip")[0][0]
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO campaign (name, creator_name, source_channel_urls, "
            "platform_board, badge, budget_note, allowed_platforms, "
            "required_hashtags, required_credit_line, required_tags_mentions, "
            "banned_content_notes, submission_instructions, status, notes) "
            "VALUES ('Pizza', '', '[]', 'other', 'open', '', '[]', '[]', '', '[]', "
            "'', '', 'active', '')"
        )
        conn.exec_driver_sql(
            "INSERT INTO autopilot_settings (campaign_id, enabled, "
            "max_clips_per_source, max_posts_per_day, draft_ttl_days, account_ids)"
            " VALUES (1, 1, 2, 3, 3, '[]')"
        )
        conn.exec_driver_sql(
            "INSERT INTO draft (clip_id, campaign_id, status, rule_results, "
            f"created_at) VALUES ({clip_id}, 1, 'pending', '[]', "
            "'2030-01-01 00:00:00')"
        )
        conn.exec_driver_sql(
            "INSERT INTO asset (kind, path, license, attribution, tags) "
            "VALUES ('sfx', 'a.wav', 'CC0', '', '[\"whoosh\"]')"
        )


def test_existing_data_is_kept_and_gets_the_defaults(
    blank_engine: Engine, rows: Rows, tmp_path: Path
) -> None:
    _v2_database(blank_engine, rows, tmp_path)
    before = {
        table: rows(f"SELECT * FROM {table}")
        for table in ("project", "clip", "campaign", "autopilot_settings", "asset")
    }
    before_columns = {table: len(_columns(rows, table)) for table in before}

    assert migrate(blank_engine, migrations_through(tmp_path, 39)) == [39]

    for table, old in before.items():
        new = rows(f"SELECT * FROM {table}")
        assert [row[: before_columns[table]] for row in new] == old
    assert rows("SELECT variant, parent_clip_id FROM clip") == [("original", None)] * 3
    assert rows("SELECT allow_heavy_edits FROM campaign") == [("unknown",)]
    assert rows(
        "SELECT enabled, proedit_enabled, proedit_preset, proedit_max_intensity "
        "FROM autopilot_settings"
    ) == [(1, 0, "clean_pro", "standard")]
    assert rows(
        "SELECT bpm, key, loudness_lufs, energy_curve, category, mood, "
        "downloaded_at, license FROM asset"
    ) == [(None, None, None, None, None, None, None, "CC0")]
    for table in (
        "pro_edit_plan",
        "edl_item",
        "pro_edit_run",
        "style_recipe",
        "style_reference",
    ):
        assert rows(f"SELECT * FROM {table}") == []
    migrate(blank_engine)
    with Session(blank_engine) as session:
        clips = [row.to_model() for row in session.exec(select(ClipRow))]
        assert [(c.variant, c.parent_clip_id) for c in clips] == [
            ("original", None)
        ] * 3
        assert get_settings_of_first(blank_engine).proedit_enabled is False


def get_settings_of_first(engine: Engine) -> Any:
    (campaign,) = campaigns.list_campaigns(engine)
    return get_settings(engine, campaign.id)


def test_a_fresh_database_has_the_new_tables_and_columns(
    engine: Engine, rows: Rows
) -> None:
    assert _columns(rows, "pro_edit_plan") == [
        "id",
        "clip_id",
        "preset",
        "intensity",
        "style_recipe_id",
        "version",
        "rationale",
        "created_by",
    ]
    assert _columns(rows, "edl_item") == [
        "plan_id",
        "item_id",
        "t_start",
        "t_end",
        "kind",
        "params",
        "reason",
        "source",
    ]
    assert _columns(rows, "pro_edit_run")[:3] == ["id", "clip_id", "plan_id"]
    assert _columns(rows, "style_recipe")[-1] == "created_at"
    assert _columns(rows, "style_reference")[-1] == "rights_confirmed_at"
    assert _columns(rows, "clip")[-2:] == ["parent_clip_id", "variant"]
    assert _columns(rows, "asset")[-7:] == [
        "bpm",
        "key",
        "loudness_lufs",
        "energy_curve",
        "category",
        "mood",
        "downloaded_at",
    ]
    assert _columns(rows, "campaign")[-1] == "allow_heavy_edits"
    assert _columns(rows, "autopilot_settings")[-3:] == [
        "proedit_enabled",
        "proedit_preset",
        "proedit_max_intensity",
    ]


def test_a_variant_clip_points_to_its_original(engine: Engine, rows: Rows) -> None:
    project_id = add_project(engine)
    original = add_clip(engine, project_id, "rendered", 70, "Bit")
    variant = add_clip(
        engine,
        project_id,
        "rendered",
        70,
        "Bit — Pro Edit",
        parent_clip_id=original,
        variant="pro_edit",
    )

    with Session(engine) as session:
        row = session.get(ClipRow, variant)
        assert row is not None
        assert (row.to_model().variant, row.to_model().parent_clip_id) == (
            "pro_edit",
            original,
        )
        assert session.get(ClipRow, original).to_model().variant == "original"  # type: ignore[union-attr]

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM clip WHERE id = {original}")
    assert rows("SELECT id FROM clip") == []


def test_clip_model_checks_its_variant() -> None:
    assert Clip.model_fields["variant"].default == "original"
    assert Clip.model_fields["parent_clip_id"].default is None
    with pytest.raises(ValidationError, match="parent_clip_id"):
        Clip.model_validate(_clip_fields() | {"variant": "pro_edit"})
    with pytest.raises(ValidationError, match="parent_clip_id"):
        Clip.model_validate(_clip_fields() | {"parent_clip_id": 3})
    with pytest.raises(ValidationError):
        Clip.model_validate(_clip_fields() | {"variant": "mine", "parent_clip_id": 3})
    variant = Clip.model_validate(
        _clip_fields() | {"variant": "pro_edit", "parent_clip_id": 3}
    )
    assert variant.parent_clip_id == 3


def _clip_fields() -> dict[str, Any]:
    from clipforge.timeline import timeline_of

    scores = dict.fromkeys(("overall", "hook", "flow", "value", "trend"), 50)
    return {
        "id": 2,
        "project_id": 1,
        "segments": [(1.0, 31.0)],
        "tracks": timeline_of([(1.0, 31.0)]),
        "title": "Bit",
        "hook_text": "Wait",
        "description": "A bit.",
        "hashtags": ["a", "b", "c"],
        "emphasis_words": [],
        "reason": "Laugh.",
        "scores": scores | {"laugh": 0.5, "energy": 0.5},
        "layout": "fill",
        "caption_template": "karaoke_bold",
        "caption_overrides": [],
        "cut_ranges": [],
        "status": "candidate",
        "output_path": None,
    }


def test_plans_items_and_runs_round_trip(engine: Engine, rows: Rows) -> None:
    project_id = add_project(engine)
    clip_id = add_clip(engine, project_id, "rendered", 70, "Bit")
    with Session(engine) as session:
        recipe = StyleRecipeRow(
            name="Phonk",
            description="Fast cuts",
            features={"cuts_per_s": {"median": 0.8, "range": [0.5, 1.2]}},
            reference_count=2,
            created_at=NOW,
        )
        session.add(recipe)
        session.commit()
        session.add(
            StyleReferenceRow(
                recipe_id=recipe.id or 0,
                url="https://x.test/a",
                rights_confirmed_at=NOW,
            )
        )
        plan = ProEditPlanRow(
            clip_id=clip_id,
            preset="skull_moment",
            intensity="pro",
            style_recipe_id=recipe.id,
            version=1,
            rationale="Punchline at 1 s",
            created_by="rule_director",
        )
        session.add(plan)
        session.commit()
        for number, kind in ((2, "freeze_frame"), (1, "zoom_punch")):
            session.add(
                EdlItemRow(
                    plan_id=plan.id or 0,
                    item_id=number,
                    t_start=number,
                    t_end=number + 0.5,
                    kind=kind,
                    params={"k": [number]},
                    reason=f"Why {number}",
                    source="manual" if number == 2 else "auto",
                )
            )
        run = ProEditRunRow(
            clip_id=clip_id,
            plan_id=plan.id,
            status="done",
            rounds=1,
            critic_scores=[
                CriticRound(
                    round=1, scores=[CriticScore(check="hook", score=8, reason="ok")]
                )
            ],
            cost_estimate=0.05,
            cost_actual=0.04,
            started_at=NOW,
            finished_at=NOW,
        )
        session.add(run)
        session.commit()

    with Session(engine) as session:
        (plan_row,) = session.exec(select(ProEditPlanRow)).all()
        items = session.exec(select(EdlItemRow)).all()
        model = plan_row.to_model(items)
        assert model == ProEditPlan(
            id=plan_row.id or 0,
            clip_id=clip_id,
            preset="skull_moment",
            intensity="pro",
            style_recipe_id=model.style_recipe_id,
            version=1,
            items=[
                EdlItem(
                    id=1,
                    t_start=1,
                    t_end=1.5,
                    kind="zoom_punch",
                    params={"k": [1]},
                    reason="Why 1",
                ),
                EdlItem(
                    id=2,
                    t_start=2,
                    t_end=2.5,
                    kind="freeze_frame",
                    params={"k": [2]},
                    reason="Why 2",
                    source="manual",
                ),
            ],
            rationale="Punchline at 1 s",
            created_by="rule_director",
        )
        recipe_model = session.exec(select(StyleRecipeRow)).one().to_model()
        assert recipe_model == StyleRecipe(
            id=recipe_model.id,
            name="Phonk",
            description="Fast cuts",
            features={"cuts_per_s": {"median": 0.8, "range": [0.5, 1.2]}},
            reference_count=2,
            created_at=NOW,
        )
        reference = session.exec(select(StyleReferenceRow)).one().to_model()
        assert reference == StyleReference(
            id=reference.id,
            recipe_id=recipe_model.id,
            url="https://x.test/a",
            rights_confirmed_at=NOW,
        )
        run_model = session.exec(select(ProEditRunRow)).one().to_model()
        assert run_model == ProEditRun(
            id=run_model.id,
            clip_id=clip_id,
            plan_id=model.id,
            status="done",
            rounds=1,
            critic_scores=[
                CriticRound(
                    round=1, scores=[CriticScore(check="hook", score=8, reason="ok")]
                )
            ],
            cost_estimate=0.05,
            cost_actual=0.04,
            started_at=NOW,
            finished_at=NOW,
        )

    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM style_recipe WHERE id = {recipe_model.id}")
    assert rows("SELECT style_recipe_id FROM pro_edit_plan") == [(None,)]
    assert rows("SELECT * FROM style_reference") == []
    with engine.begin() as conn:
        conn.exec_driver_sql(f"DELETE FROM clip WHERE id = {clip_id}")
    for table in ("pro_edit_plan", "edl_item", "pro_edit_run"):
        assert rows(f"SELECT * FROM {table}") == []


def test_a_clip_has_one_plan_per_version_and_an_item_number_once(
    engine: Engine,
) -> None:
    clip_id = add_clip(engine, add_project(engine), "rendered", 70)
    plan = {
        "clip_id": clip_id,
        "preset": "glitch",
        "intensity": "clean",
        "created_by": "user",
    }
    with Session(engine) as session:
        first = ProEditPlanRow(**plan, version=1)
        session.add_all([first, ProEditPlanRow(**plan, version=2)])
        session.commit()
        first_id = first.id or 0
        session.add(EdlItemRow(plan_id=first_id, item_id=1, **_item_fields()))
        session.commit()
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(ProEditPlanRow(**plan, version=2))
        session.commit()
    with Session(engine) as session, pytest.raises(IntegrityError):
        session.add(EdlItemRow(plan_id=first_id, item_id=1, **_item_fields()))
        session.commit()


def _item_fields() -> dict[str, Any]:
    return {"t_start": 0.0, "t_end": 1.0, "kind": "flash", "params": {}, "reason": "x"}


def test_edl_item_and_plan_are_validated() -> None:
    assert EdlItem.model_validate(ITEM).source == "auto"
    for change in (
        {"t_start": 2.0},
        {"t_start": -0.1},
        {"kind": "explode"},
        {"reason": ""},
        {"reason": "  "},
        {"source": "robot"},
        {"id": 0},
    ):
        with pytest.raises(ValidationError):
            EdlItem.model_validate(ITEM | change)
    plan: dict[str, Any] = {
        "id": 1,
        "clip_id": 2,
        "preset": "clean_pro",
        "intensity": "standard",
        "version": 1,
        "created_by": "director",
    }
    assert ProEditPlan.model_validate(plan).items == []
    with pytest.raises(ValidationError, match="unique"):
        ProEditPlan.model_validate(plan | {"items": [ITEM, ITEM]})
    for change in (
        {"preset": "wild"},
        {"intensity": "max"},
        {"version": 0},
        {"created_by": "me"},
    ):
        with pytest.raises(ValidationError):
            ProEditPlan.model_validate(plan | change)


def test_audio_fields_of_an_asset_round_trip(engine: Engine) -> None:
    with Session(engine) as session:
        row = AssetRow(
            kind="music",
            path="beat.wav",
            license="CC BY 4.0",
            attribution="By A",
            source_url="https://freesound.org/s/1/",
            tags=["phonk"],
            bpm=140.0,
            key="F minor",
            loudness_lufs=-12.5,
            energy_curve=[0.1, 0.9],
            category="loop",
            mood="dark",
            downloaded_at=NOW,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        asset = row.to_model()
    assert (asset.bpm, asset.key, asset.loudness_lufs) == (140.0, "F minor", -12.5)
    assert (asset.energy_curve, asset.category, asset.mood) == (
        [0.1, 0.9],
        "loop",
        "dark",
    )
    with Session(engine) as session:
        stored = session.get(AssetRow, row.id)
        assert stored is not None
        assert stored.energy_curve == [0.1, 0.9]
        assert stored.downloaded_at is not None


def test_campaign_heavy_edits_switch(engine: Engine) -> None:
    assert CampaignCreate(name="A").allow_heavy_edits == "unknown"
    campaign = new_campaign(engine)
    assert campaign.allow_heavy_edits == "unknown"
    patched = campaigns.update_campaign(
        engine, campaign.id, CampaignPatch(allow_heavy_edits="true")
    )
    assert patched.allow_heavy_edits == "true"
    assert campaigns.get_campaign(engine, campaign.id).allow_heavy_edits == "true"
    with pytest.raises(ValidationError):
        CampaignCreate(name="A", allow_heavy_edits="yes")  # type: ignore[arg-type]


def test_autopilot_proedit_settings(engine: Engine) -> None:
    campaign = new_campaign(engine)
    defaults = get_settings(engine, campaign.id)
    assert (
        defaults.proedit_enabled,
        defaults.proedit_preset,
        defaults.proedit_max_intensity,
    ) == (False, "clean_pro", "standard")

    saved = save_settings(
        engine,
        campaign.id,
        AutopilotSettingsUpdate(
            proedit_enabled=True,
            proedit_preset="phonk_edit",
            proedit_max_intensity="pro",
        ),
    )

    assert (
        saved.proedit_enabled,
        saved.proedit_preset,
        saved.proedit_max_intensity,
    ) == (
        True,
        "phonk_edit",
        "pro",
    )
    assert get_settings(engine, campaign.id) == saved
    for change in ({"proedit_preset": "wild"}, {"proedit_max_intensity": "max"}):
        with pytest.raises(ValidationError):
            AutopilotSettingsUpdate.model_validate(change)
