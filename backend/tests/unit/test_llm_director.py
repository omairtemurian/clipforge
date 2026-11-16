"""The LLM Director (SPEC-v3 3.5, TASK-221) with recorded LLM replies: a
valid plan, an invalid reply then a valid one, always-invalid replies and
an unreachable LLM (both fall back to the rule-based Director), the prompt
it sends, and the tokens it meters."""

import json
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import httpx
from clipforge.asset_rows import UsageRecordRow
from clipforge.llm import OpenAICompatClient
from clipforge.models import Campaign, StyleRecipe
from clipforge.proedit.beats import MusicGrid
from clipforge.proedit.budgets import budget_problems, effective_budget
from clipforge.proedit.config import ProEditConfig
from clipforge.proedit.director_catalog import asset_catalog
from clipforge.proedit.director_cost import MAX_CALLS, PROEDIT
from clipforge.proedit.director_llm import NO_LLM, director_plan, reply_plan
from clipforge.proedit.director_music import MusicChoice
from clipforge.proedit.director_prompt import (
    DirectorRequest,
    director_input,
    system_prompt,
    user_prompt,
)
from clipforge.proedit.edl import validate_plan
from clipforge.proedit.preset_defs import get_preset
from clipforge.proedit.signal_models import ProEditSignals
from fakes import FakeLLMClient, openai_reply
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session, select

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
REPLIES = FIXTURES / "proedit_director"
VALID = REPLIES / "valid_phonk_pro.json"
INVALID = REPLIES / "invalid_phonk_pro.json"
SIGNALS = ProEditSignals.model_validate(
    json.loads((FIXTURES / "proedit_signals_expected.json").read_text())
)
BEATS = [round(n * 60 / 140, 4) for n in range(70)]
MUSIC = MusicChoice(
    "night_drive",
    MusicGrid(duration=30, bpm=140, beats=BEATS, downbeats=BEATS[::4]),
    1.0,
)
PRICED = ProEditConfig(usd_per_million_tokens=2.0)
NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)


def request(**changes: object) -> DirectorRequest:
    fields: dict[str, object] = {
        "signals": SIGNALS,
        "preset": get_preset("phonk_edit"),
        "preset_id": "phonk_edit",
        "intensity": "pro",
        "music": MUSIC,
        "catalog": tuple(asset_catalog()),
        "plan_id": 4,
    } | changes
    return DirectorRequest(**fields)  # type: ignore[arg-type]


class SequenceServer:
    """An OpenAI-compatible server that answers each request with the next
    reply (a body, or an HTTP status for a failure) and keeps the requests."""

    def __init__(self, *replies: str | int, tokens: tuple[int, int] = (900, 100)):
        self.replies: deque[str | int] = deque(replies)
        self.tokens = tokens
        self.requests: list[dict[str, object]] = []

    def client(self) -> OpenAICompatClient:
        transport = httpx.MockTransport(self._handle)
        return OpenAICompatClient(
            "https://llm.test/v1", "key", "m", transport=transport
        )

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        reply = self.replies.popleft()
        if isinstance(reply, int):
            return httpx.Response(reply, json={"error": "down"})
        return httpx.Response(200, json=openai_reply(reply, tokens=self.tokens))

    def user_message(self, n: int) -> str:
        messages = self.requests[n]["messages"]
        assert isinstance(messages, list)
        return str(messages[-1]["content"])


def proedit_records(engine: Engine) -> list[UsageRecordRow]:
    with Session(engine) as session:
        query = select(UsageRecordRow).where(UsageRecordRow.kind == PROEDIT)
        return list(session.exec(query).all())


def test_a_valid_reply_becomes_the_plan_after_post_processing(engine: Engine) -> None:
    project_id = add_project(engine)
    server = SequenceServer(VALID.read_text())

    result = director_plan(
        request(), server.client(), engine=engine, project_id=project_id, cfg=PRICED
    )

    plan = result.plan
    assert (result.fallback, result.calls, result.invalid_replies) == (None, 1, [])
    assert (plan.created_by, plan.id, plan.preset, plan.intensity) == (
        "director",
        4,
        "phonk_edit",
        "pro",
    )
    assert plan.rationale.startswith("Phonk Edit at pro")
    validate_plan(plan, SIGNALS.duration)
    budget = effective_budget("pro", get_preset("phonk_edit").budgets.get("pro"))
    assert budget_problems(plan.items, budget, SIGNALS.duration) == []
    assert {n.action for n in result.notes} >= {"moved", "dropped"}
    cheese = [i for i in plan.items if i.kind == "zoom_punch" and i.t_start > 15]
    assert cheese and abs(cheese[0].t_start - 15.9333) < 1e-3
    assert any(i.params.get("asset") == "impact_boom" for i in plan.items)
    (record_,) = proedit_records(engine)
    assert (record_.project_id, record_.units) == (project_id, 1000)
    assert record_.cost_usd is not None and abs(record_.cost_usd - 0.002) < 1e-9
    assert result.tokens == 1000
    assert result.cost_usd is not None and abs(result.cost_usd - 0.002) < 1e-9


def test_an_invalid_reply_is_retried_with_its_problems(engine: Engine) -> None:
    server = SequenceServer(INVALID.read_text(), VALID.read_text())

    result = director_plan(request(), server.client(), engine=engine, cfg=PRICED)

    assert (result.fallback, result.calls) == (None, 2)
    assert result.plan.created_by == "director"
    (problems,) = result.invalid_replies
    assert "item 2 (glitch): the Phonk Edit preset does not use glitch" in problems
    assert any("air_horn" in p for p in problems)
    assert any("overlap on the zoom track" in p for p in problems)
    retry = server.user_message(1)
    assert "Your previous reply was not valid" in retry
    assert "does not use glitch" in retry
    assert "previous reply" not in server.user_message(0)
    assert len(proedit_records(engine)) == 2
    assert result.tokens == 2000


def test_always_invalid_replies_fall_back_to_the_rule_based_plan() -> None:
    llm = FakeLLMClient(INVALID, "not json", '{"items": []}')

    result = director_plan(request(), llm, cfg=PRICED)

    assert result.calls == MAX_CALLS == 3
    assert len(llm.calls) == 3
    assert result.fallback == "the LLM sent no valid plan in 3 tries"
    assert result.plan.created_by == "rule_director"
    assert result.plan.id == 4
    assert len(result.invalid_replies) == 3
    assert result.invalid_replies[2] == ["rationale: Field required"]
    validate_plan(result.plan, SIGNALS.duration)


def test_no_llm_or_a_failing_llm_gives_the_rule_based_plan() -> None:
    without = director_plan(request(), None)
    assert (without.fallback, without.calls, without.estimate) == (NO_LLM, 0, None)
    assert without.plan.created_by == "rule_director"

    server = SequenceServer(500)
    failed = director_plan(request(), server.client(), cfg=PRICED)
    assert failed.fallback is not None
    assert failed.fallback.startswith("the LLM request failed:")
    assert (failed.calls, failed.plan.created_by) == (1, "rule_director")
    assert failed.plan.items == without.plan.items


def test_the_prompt_holds_the_signals_rules_catalog_and_constraints() -> None:
    recipe = StyleRecipe(
        id=9,
        name="Fast cuts",
        description="punchy",
        features={
            "cuts_per_10s": 6.0,
            "targets": {"metrics": {"bpm": {"median": 140, "low": 130, "high": 150}}},
        },
        created_at=NOW,
    )
    campaign = Campaign.model_construct(
        allow_heavy_edits=False, banned_content_notes="no gore"
    )
    req = request(recipe=recipe, campaign=campaign)

    system, user = system_prompt(req.preset), director_input(req)

    assert '"zoom_punch"' in system
    assert "$params" not in system and "$tracks" not in system
    assert user_prompt(req).endswith(
        json.dumps(user, separators=(",", ":"), ensure_ascii=False)
    )
    assert user["signals"]["clip"]["duration"] == 18.0
    words = user["signals"]["transcript"]
    assert ["night." in str(w) for w in words].count(True) == 1
    assert user["signals"]["music"]["bpm"] == 140
    assert user["intensity"] == "pro"
    assert user["style_recipe"]["name"] == "Fast cuts"
    assert "features" not in user["style_recipe"]
    assert user["style_recipe"]["targets"]["metrics"]["bpm"]["target"] == 140
    assert user["campaign"]["banned_content_notes"] == "no gore"
    ids = {a["id"] for a in user["asset_catalog"]}
    assert "impact_boom" in ids and "night_drive" in ids


def test_reply_plan_reports_kinds_assets_and_bad_json() -> None:
    req = request()
    plan, problems = reply_plan("{not json", req)
    assert plan is None and problems[0].startswith("reply: Invalid JSON")

    skull = request(preset=get_preset("skull_moment"), preset_id="skull_moment")

    def overlay(asset: str) -> str:
        item = {"kind": "overlay", "t_start": 1, "t_end": 2, "params": {"asset": asset}}
        return json.dumps({"rationale": "r", "items": [item | {"reason": "a laugh"}]})

    plan, problems = reply_plan(overlay("emoji:😂"), skull)
    assert problems == [] and plan is not None
    plan, problems = reply_plan(overlay("no_such_overlay"), skull)
    assert plan is None and len(problems) == 1 and "no_such_overlay" in problems[0]
