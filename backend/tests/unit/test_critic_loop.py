"""The Pro Edit critic's revision loop (SPEC-v3 3.7, TASK-223) with recorded
vision replies: the critic's EDL changes applied by code with validation
(invalid ones ignored with the reason), "what changed" per round, the
round limit, the early stop when every score passes, the monthly cap
blocking further rounds, and the director-only and failure stops.

The proxy render and its frame/audio sampling are covered by
pipeline/test_critic_media.py; here render returns a path and the critic
request is built from the plan with fixed frames."""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from clipforge.llm import OpenAICompatClient
from clipforge.models import CriticRound, EdlItem, ProEditPlan
from clipforge.proedit.config import ProEditConfig
from clipforge.proedit.critic import revise
from clipforge.proedit.critic.apply import (
    BY_POST_PROCESSING,
    plan_diff,
    revise_plan,
)
from clipforge.proedit.critic.changes import CriticChange
from clipforge.proedit.critic.prompt import CriticReply, CriticRequest
from clipforge.proedit.critic.score import estimate_critic_cost, parse_reply
from clipforge.proedit.director_catalog import CatalogAsset, asset_catalog
from clipforge.proedit.director_prompt import DirectorRequest
from clipforge.proedit.director_rules import rule_plan
from clipforge.proedit.edl import validate_plan
from clipforge.proedit.preset_defs import get_preset
from critic_fakes import SEES_RED, SIGNALS, ReplyServer, audio, frames, scores_reply
from fakes import openai_reply
from pydantic import TypeAdapter, ValidationError
from seed import add_project
from sqlalchemy import Engine

PRESET = "clean_pro"
NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
PROBE = openai_reply(SEES_RED, tokens=(80, 5))
CHANGES: TypeAdapter[list[CriticChange]] = TypeAdapter(list[CriticChange])


def cfg(**fields: Any) -> ProEditConfig:
    return ProEditConfig(usd_per_million_tokens=2.0, **fields)


def director_request() -> DirectorRequest:
    return DirectorRequest(
        signals=SIGNALS,
        preset=get_preset(PRESET),
        preset_id=PRESET,
        intensity="pro",
        catalog=tuple(asset_catalog()),
        plan_id=4,
    )


def base_plan() -> ProEditPlan:
    request = director_request()
    return rule_plan(SIGNALS, request.preset, PRESET, "pro", None, plan_id=4).plan


def item(plan: ProEditPlan, item_id: int) -> EdlItem:
    return next(i for i in plan.items if i.id == item_id)


def changes(*raw: dict[str, Any]) -> list[CriticChange]:
    return CHANGES.validate_python(list(raw))


def reply(scores: dict[str, float], *raw: dict[str, Any]) -> dict[str, Any]:
    body = json.loads(scores_reply(**scores))
    body["changes"] = list(raw)
    return openai_reply(json.dumps(body), tokens=(1500, 300))


LOW = {"hook": 4.0}
SCALE_UP = {
    "op": "modify",
    "item_id": 3,
    "params": {"scale": 1.2},
    "reason": "the hook punch is too weak",
}
DROP_PUNCH = {
    "op": "remove",
    "item_id": 8,
    "reason": "too many punches mid-clip",
}


@dataclass
class Proxy:
    """The fake proxy renders: a path per plan version, and the plans
    rendered in order."""

    rendered: list[ProEditPlan] = field(default_factory=list)

    def __call__(self, plan: ProEditPlan) -> Path:
        self.rendered.append(plan)
        return Path(f"/proxy/v{plan.version}.mp4")


@pytest.fixture(autouse=True)
def fixed_frames(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def request(
        video: Path,
        plan: ProEditPlan,
        preset: Any,
        signals: Any,
        cfg: ProEditConfig,
        catalog: tuple[CatalogAsset, ...] = (),
    ) -> CriticRequest:
        assert video == Path(f"/proxy/v{plan.version}.mp4")
        return CriticRequest(
            plan=plan,
            preset=preset,
            signals=signals,
            frames=frames(0.0, 1.0, 2.0),
            audio=audio(),
            threshold=cfg.critic_threshold,
            catalog=catalog,
        )

    monkeypatch.setattr(revise, "critic_request", request)
    yield


def client(server: ReplyServer) -> OpenAICompatClient:
    return OpenAICompatClient(
        "https://llm.test/v1", "key", "vis-1", transport=server.transport
    )


def sent_input(server: ReplyServer, n: int) -> dict[str, Any]:
    parts = server.body(n)["messages"][1]["content"]
    sent: dict[str, Any] = json.loads(parts[0]["text"])
    return sent


def test_the_rounds_are_capped_and_each_stores_what_changed(engine: Engine) -> None:
    plan = base_plan()
    server = ReplyServer(PROBE, reply(LOW, SCALE_UP), reply(LOW, DROP_PUNCH))
    proxy, progress = Proxy(), list[tuple[int, int]]()

    def store(revision: ProEditPlan) -> ProEditPlan:
        return revision.model_copy(update={"id": 100 + revision.version})

    result = revise.critic_loop(
        plan,
        director_request(),
        proxy,
        client(server),
        engine=engine,
        project_id=add_project(engine),
        cfg=cfg(),
        now=NOW,
        store=store,
        on_round=lambda n, total: progress.append((n, total)),
    )

    assert result.stopped == "max_rounds"
    assert progress == [(1, 2), (2, 2)]
    assert [p.version for p in proxy.rendered] == [1, 2]
    assert [(p.id, p.version) for p in result.revisions] == [(102, 2), (103, 3)]
    assert result.plan == result.revisions[-1]
    assert {p.created_by for p in result.revisions} == {"critic_revision"}
    assert result.calls == 2 and len(server.requests) == 3
    assert result.tokens == 85 + 2 * 1800
    assert result.cost_usd == pytest.approx((85 + 2 * 1800) * 2e-6)
    first, second = result.rounds
    assert (first.round, first.plan_version, second.plan_version) == (1, 1, 2)
    assert first.scores[0].check == "hook" and first.scores[0].score == 4
    (scaled,) = first.changes
    assert (scaled.op, scaled.item_id, scaled.reason) == (
        "modify",
        3,
        "the hook punch is too weak",
    )
    assert scaled.before == item(plan, 3)
    assert scaled.after is not None and scaled.after.params["scale"] == 1.2
    (dropped,) = second.changes
    assert (dropped.op, dropped.item_id, dropped.after) == ("remove", 8, None)
    assert first.ignored == second.ignored == []
    assert {i.id for i in result.plan.items} == {i.id for i in plan.items} - {8}
    validate_plan(result.plan, SIGNALS.duration)
    assert any(
        row["id"] == 3 and row["params"]["scale"] == 1.1
        for row in sent_input(server, 1)["edl"]
    )
    assert any(
        row["id"] == 3 and row["params"]["scale"] == 1.2
        for row in sent_input(server, 2)["edl"]
    )


def test_every_score_passing_stops_the_loop_early() -> None:
    plan = base_plan()
    server = ReplyServer(PROBE, reply(LOW, SCALE_UP), reply({}, DROP_PUNCH))
    proxy = Proxy()

    result = revise.critic_loop(
        plan, director_request(), proxy, client(server), cfg=cfg(critic_max_rounds=3)
    )

    assert result.stopped == "passed"
    assert len(result.rounds) == 2 and len(proxy.rendered) == 2
    assert len(result.revisions) == 1
    assert result.rounds[1].changes == [] and result.rounds[1].ignored == []
    assert item(result.plan, 8) == item(plan, 8)
    assert sent_input(server, 1)["threshold"] == 7


def test_the_threshold_decides_what_passes() -> None:
    server = ReplyServer(PROBE, reply(LOW, SCALE_UP))

    result = revise.critic_loop(
        base_plan(),
        director_request(),
        Proxy(),
        client(server),
        cfg=cfg(critic_threshold=4),
    )

    assert result.stopped == "passed"
    assert result.revisions == [] and result.plan == base_plan()


def test_zero_rounds_runs_no_critic() -> None:
    server = ReplyServer()
    proxy = Proxy()

    result = revise.critic_loop(
        base_plan(),
        director_request(),
        proxy,
        client(server),
        cfg=cfg(critic_max_rounds=0),
    )

    assert (result.stopped, result.rounds, result.calls) == ("off", [], 0)
    assert proxy.rendered == [] and server.requests == []


def test_the_round_limit_is_zero_to_three() -> None:
    assert ProEditConfig().critic_max_rounds == 2
    for bad in (-1, 4):
        with pytest.raises(ValidationError):
            ProEditConfig(critic_max_rounds=bad)


def test_invalid_changes_are_ignored_with_the_reason() -> None:
    plan = base_plan()
    plan.items.append(
        EdlItem(
            id=12,
            kind="sfx",
            t_start=13.0,
            t_end=13.3,
            params={"asset": "whoosh_swift"},
            reason="the user's whoosh",
            source="manual",
        )
    )
    asked = changes(
        {"op": "remove", "item_id": 99, "reason": "gone"},
        {"op": "remove", "item_id": 12, "reason": "the user's whoosh distracts"},
        {"op": "add", "kind": "glitch", "t_start": 1.0, "t_end": 1.2, "reason": "x"},
        {
            "op": "add",
            "kind": "zoom_punch",
            "t_start": 0.5,
            "t_end": 0.9,
            "reason": "punch the hook",
        },
        {"op": "modify", "item_id": 7, "t_end": 30.0, "reason": "hold longer"},
        {
            "op": "add",
            "kind": "sfx",
            "t_start": 2.0,
            "t_end": 2.4,
            "params": {"asset": "no_such_sound"},
            "reason": "a ding",
        },
        {"op": "modify", "item_id": 3, "params": {"scale": "big"}, "reason": "y"},
        {
            "op": "add",
            "kind": "text_pop",
            "t_start": 8.0,
            "t_end": 8.6,
            "params": {"text": "WAIT"},
            "reason": "a pattern interrupt in the long setup",
        },
    )

    revision = revise_plan(plan, asked, director_request())

    problems = {(i.op, i.item_id, i.kind): i.problem for i in revision.ignored}
    assert problems[("remove", 99, None)] == "item 99 is not in the plan"
    assert problems[("remove", 12, None)] == "item 12 (sfx) was placed by the user"
    assert (
        problems[("add", None, "glitch")] == "the Clean Pro preset does not use glitch"
    )
    assert "overlap on the zoom track" in problems[("add", None, "zoom_punch")]
    assert "past the clip end at 18 s" in problems[("modify", 7, None)]
    assert "'no_such_sound' is not a sfx asset" in problems[("add", None, "sfx")]
    assert "scale" in problems[("modify", 3, None)]
    assert len(revision.ignored) == 7
    assert {i.reason for i in revision.ignored} >= {
        "gone",
        "the user's whoosh distracts",
    }
    assert revision.plan is not None
    (added,) = [
        c
        for c in revision.changes
        if c.op == "add" and c.after and c.after.kind == "text_pop"
    ]
    assert added.item_id == 13 and added.before is None
    assert added.reason == "a pattern interrupt in the long setup"
    assert added.after is not None and added.after.params["text"] == "WAIT"
    assert item(revision.plan, 12) == item(plan, 12)
    assert item(revision.plan, 3) == item(plan, 3)
    # The new pop pushes the setup's window over the pro budget: the
    # lowest-priority effect (the zoom push) is dropped, and the diff says so.
    pushed = next(c for c in revision.changes if c.item_id == 9)
    assert (pushed.op, pushed.after) == ("remove", None)
    assert pushed.reason.startswith("dropped by post-processing: over the pro")
    assert any(n.startswith("item 9 (zoom_push) dropped") for n in revision.notes)
    validate_plan(revision.plan, SIGNALS.duration)


def test_an_added_item_the_budget_drops_is_reported_as_ignored() -> None:
    plan = base_plan()
    crowd = [
        {
            "op": "add",
            "kind": "text_pop",
            "t_start": t,
            "t_end": t + 0.5,
            "params": {"text": f"POP{n}"},
            "reason": f"pop {n}",
        }
        for n, t in enumerate((3.4, 3.9, 4.4))
    ]

    revision = revise_plan(plan, changes(*crowd), director_request())

    dropped = [i for i in revision.ignored if i.kind == "text_pop"]
    assert dropped, "three pops at once must pass the pro budget"
    assert all(
        i.problem.startswith("dropped by post-processing: over the pro")
        for i in dropped
    )
    kept = {c.reason for c in revision.changes if c.op == "add"}
    assert kept | {i.reason for i in dropped} == {"pop 0", "pop 1", "pop 2"}


def test_a_round_whose_changes_are_all_ignored_stops_the_loop() -> None:
    plan = base_plan()
    bad = {"op": "remove", "item_id": 99, "reason": "gone"}
    server = ReplyServer(PROBE, reply(LOW, bad))

    result = revise.critic_loop(
        plan, director_request(), Proxy(), client(server), cfg=cfg()
    )

    assert result.stopped == "no_changes"
    assert result.plan == plan and result.revisions == []
    (only,) = result.rounds
    assert [(i.item_id, i.problem) for i in only.ignored] == [
        (99, "item 99 is not in the plan")
    ]


def test_the_monthly_cap_blocks_further_rounds(engine: Engine) -> None:
    project_id = add_project(engine)
    plan = base_plan()
    one_call = estimate_critic_cost(
        CriticRequest(
            plan=plan,
            preset=get_preset(PRESET),
            signals=SIGNALS,
            frames=frames(0.0, 1.0, 2.0),
            audio=audio(),
            catalog=tuple(asset_catalog()),
        ),
        cfg(),
    ).usd
    assert one_call is not None
    # Round 1 fits (the probe spent $0.00017); after its $0.0036 call the
    # next round would pass the cap.
    capped = cfg(monthly_cap_usd=one_call + 0.001)
    server = ReplyServer(PROBE, reply(LOW, SCALE_UP))
    proxy = Proxy()

    result = revise.critic_loop(
        plan,
        director_request(),
        proxy,
        client(server),
        engine=engine,
        project_id=project_id,
        cfg=capped,
        now=NOW,
    )

    assert result.stopped == "cap"
    assert len(result.rounds) == 1 and len(result.revisions) == 1
    assert len(proxy.rendered) == 1 and len(server.requests) == 2
    assert result.message is not None
    assert result.message.startswith("The Pro Edit monthly cap of")
    assert "the critic's next round needs about" in result.message
    assert result.plan == result.revisions[0]


def test_a_cap_reached_before_the_first_call_keeps_the_plan(engine: Engine) -> None:
    plan = base_plan()
    server = ReplyServer(PROBE)

    result = revise.critic_loop(
        plan,
        director_request(),
        Proxy(),
        client(server),
        engine=engine,
        cfg=cfg(monthly_cap_usd=0.0001),
        now=NOW,
    )

    assert (result.stopped, result.rounds, result.plan) == ("cap", [], plan)
    assert result.calls == 0 and len(server.requests) == 1


def test_no_vision_stops_before_rendering() -> None:
    proxy = Proxy()

    result = revise.critic_loop(
        base_plan(), director_request(), proxy, client(ReplyServer(400)), cfg=cfg()
    )

    assert result.stopped == "director_only"
    assert result.message is not None and "does not accept images" in result.message
    assert proxy.rendered == [] and result.rounds == []
    no_llm = revise.critic_loop(base_plan(), director_request(), proxy, None, cfg=cfg())
    assert no_llm.stopped == "director_only" and proxy.rendered == []


def test_a_failing_llm_keeps_the_last_plan() -> None:
    server = ReplyServer(PROBE, reply(LOW, SCALE_UP), 503)

    result = revise.critic_loop(
        base_plan(), director_request(), Proxy(), client(server), cfg=cfg()
    )

    assert result.stopped == "failed"
    assert result.message is not None
    assert result.message.startswith("the LLM request failed:")
    assert len(result.rounds) == 1 and result.plan == result.revisions[0]


def test_a_malformed_change_makes_the_reply_invalid() -> None:
    body = json.loads(scores_reply())
    body["changes"] = [{"op": "replace", "item_id": 3, "reason": "x"}]
    parsed, problems = parse_reply(json.dumps(body))
    assert parsed is None and any("changes.0" in p for p in problems)
    body["changes"] = [{"op": "modify", "item_id": 3, "reason": "nothing"}]
    assert parse_reply(json.dumps(body))[0] is None
    body["changes"] = [SCALE_UP]
    parsed, _ = parse_reply(json.dumps(body))
    assert isinstance(parsed, CriticReply) and len(parsed.changes) == 1


def test_the_diff_names_post_processing_when_the_critic_did_not() -> None:
    plan = base_plan()
    moved = item(plan, 3).model_copy(update={"t_start": 0.5})
    after = [moved if i.id == 3 else i for i in plan.items if i.id != 8]

    diff = plan_diff(plan.items, after, {8: "too many punches"})

    assert [(c.op, c.item_id, c.reason) for c in diff] == [
        ("modify", 3, BY_POST_PROCESSING),
        ("remove", 8, "too many punches"),
    ]


def test_a_round_round_trips_as_stored_json() -> None:
    server = ReplyServer(PROBE, reply(LOW, SCALE_UP))
    result = revise.critic_loop(
        base_plan(),
        director_request(),
        Proxy(),
        client(server),
        cfg=cfg(critic_max_rounds=1),
    )

    (stored,) = result.rounds
    assert CriticRound.model_validate_json(stored.model_dump_json()) == stored
    assert CriticRound(round=1, scores=[]).changes == []
