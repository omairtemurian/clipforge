"""The Pro Edit critic's scores (SPEC-v3 3.7, 1.6, TASK-222) with recorded
vision replies: the checklist scores of a valid reply, the request it sends
(frame rows in image order), retries of invalid replies, a model without
vision (Director only, no critic call), the monthly cap, a failing LLM, the
cost estimate and the metered tokens."""

import json
from datetime import UTC, datetime

from clipforge.asset_rows import UsageRecordRow
from clipforge.llm import OpenAICompatClient
from clipforge.models import CriticScore
from clipforge.proedit.config import ProEditConfig
from clipforge.proedit.critic.capability import DIRECTOR_ONLY
from clipforge.proedit.critic.prompt import (
    CHECKS,
    critic_input,
    system_prompt,
    user_prompt,
)
from clipforge.proedit.critic.score import (
    below_threshold,
    critique,
    estimate_critic_cost,
    passes,
    reply_scores,
)
from clipforge.proedit.director_cost import MAX_CALLS, PROEDIT, tokens_of
from critic_fakes import SEES_RED, ReplyServer, critic_request, scores_reply
from fakes import openai_reply
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session, select

PRICED = ProEditConfig(usd_per_million_tokens=2.0)
NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
PROBE = openai_reply(SEES_RED, tokens=(80, 5))


def client(server: ReplyServer) -> OpenAICompatClient:
    return OpenAICompatClient(
        "https://llm.test/v1", "key", "vis-1", transport=server.transport
    )


def reply(content: str) -> dict[str, object]:
    return openai_reply(content, tokens=(1500, 300))


def user_text(server: ReplyServer, n: int) -> str:
    parts = server.body(n)["messages"][1]["content"]
    return str(parts[0]["text"])


def proedit_records(engine: Engine) -> list[UsageRecordRow]:
    with Session(engine) as session:
        query = select(UsageRecordRow).where(UsageRecordRow.kind == PROEDIT)
        return list(session.exec(query).all())


def test_a_vision_reply_becomes_the_checklist_scores(engine: Engine) -> None:
    project_id = add_project(engine)
    server = ReplyServer(PROBE, reply(scores_reply(hook=4, loop_ending=6.5)))

    result = critique(
        critic_request(),
        client(server),
        engine=engine,
        project_id=project_id,
        cfg=PRICED,
        now=NOW,
    )

    assert (result.director_only, result.message, result.failure) == (False, None, None)
    assert [s.check for s in result.scores] == list(CHECKS)
    by_check = {s.check: s.score for s in result.scores}
    assert by_check == {c: 8 for c in CHECKS} | {"hook": 4, "loop_ending": 6.5}
    assert result.scores[0] == CriticScore(
        check="hook", score=4, reason="hook at 1.2 s"
    )
    assert (result.calls, result.invalid_replies) == (1, [])
    assert result.tokens == 85 + 1800
    assert result.cost_usd == (85 + 1800) * 2 / 1_000_000
    records = proedit_records(engine)
    assert sorted(r.units for r in records) == [85, 1800]
    assert {r.project_id for r in records} == {project_id}
    assert [s.check for s in below_threshold(result.scores, 7)] == [
        "hook",
        "loop_ending",
    ]
    assert not passes(result.scores, 7)
    assert passes(result.scores, 4)


def test_the_request_sends_the_frames_in_order_with_their_rows() -> None:
    request = critic_request(n_frames=3)
    server = ReplyServer(PROBE, reply(scores_reply()))

    critique(request, client(server), cfg=PRICED)

    body = server.body(1)
    assert body["messages"][0] == {"role": "system", "content": system_prompt()}
    parts = body["messages"][1]["content"]
    assert [p["type"] for p in parts] == ["text"] + ["image_url"] * 3
    urls = [p["image_url"]["url"] for p in parts[1:]]
    assert urls == [f.image.data_url() for f in request.frames]
    sent = json.loads(parts[0]["text"])
    assert sent == critic_input(request)
    assert sent["frames"] == [
        {"image": 1, "t": 0.0, "why": ["1 fps baseline"]},
        {"image": 2, "t": 1.0, "why": ["1 fps baseline"]},
        {"image": 3, "t": 2.0, "why": ["1 fps baseline"]},
    ]
    assert (sent["preset"]["id"], sent["intensity"]) == ("phonk_edit", "pro")
    assert [i["kind"] for i in sent["edl"]] == ["zoom_punch", "text_pop"]
    assert sent["audio"]["speech_over_music_db"] == 13.0
    assert len(sent["transcript"]) == len(request.signals.words)


def test_the_system_prompt_lists_every_check_and_the_schema() -> None:
    prompt = system_prompt()

    for check, text in CHECKS.items():
        assert f"- {check}: {text}" in prompt
    assert '"scores"' in prompt
    assert "$checklist" not in prompt and "$schema" not in prompt


def test_an_invalid_reply_is_sent_back_with_its_problems() -> None:
    missing = json.loads(scores_reply())
    missing["scores"] = [s for s in missing["scores"] if s["check"] != "loop_ending"]
    server = ReplyServer(PROBE, reply(json.dumps(missing)), reply(scores_reply()))

    result = critique(critic_request(), client(server), cfg=PRICED)

    assert result.failure is None
    assert result.calls == 2
    (problems,) = result.invalid_replies
    assert any(p.endswith("missing checks: loop_ending") for p in problems)
    retry = user_text(server, 2)
    assert "Your previous reply was not valid" in retry
    assert "missing checks: loop_ending" in retry
    assert len(result.scores) == len(CHECKS)


def test_no_valid_reply_in_every_try_gives_no_scores() -> None:
    bad = reply('{"scores": [{"check": "hook", "score": 11, "reason": "x"}]}')
    server = ReplyServer(PROBE, *[bad] * MAX_CALLS)

    result = critique(critic_request(), client(server), cfg=PRICED)

    assert result.scores == []
    assert result.calls == MAX_CALLS
    assert len(result.invalid_replies) == MAX_CALLS
    assert result.failure == f"the LLM sent no valid scores in {MAX_CALLS} tries"
    assert not result.director_only


def test_a_model_without_vision_runs_the_director_only() -> None:
    server = ReplyServer(400)

    result = critique(critic_request(), client(server), cfg=PRICED)

    assert result.director_only
    assert result.message == f"The model vis-1 does not accept images: {DIRECTOR_ONLY}"
    assert (result.scores, result.calls, result.estimate) == ([], 0, None)
    assert len(server.requests) == 1
    assert not passes(result.scores, 0)


def test_no_llm_runs_the_director_only() -> None:
    result = critique(critic_request(), None, cfg=PRICED)

    assert result.director_only
    assert result.message == f"No LLM is configured: {DIRECTOR_ONLY}"
    assert (result.tokens, result.cost_usd) == (0, None)


def test_the_monthly_cap_stops_the_critic(engine: Engine) -> None:
    capped = ProEditConfig(usd_per_million_tokens=2.0, monthly_cap_usd=0.001)
    server = ReplyServer(PROBE)

    result = critique(
        critic_request(), client(server), engine=engine, cfg=capped, now=NOW
    )

    assert result.scores == []
    assert result.calls == 0
    assert result.failure is not None
    assert result.failure.startswith("The Pro Edit monthly cap of $0.0010 is reached")
    assert "the critic needs about" in result.failure
    assert len(server.requests) == 1


def test_a_failing_llm_gives_no_scores() -> None:
    server = ReplyServer(PROBE, 503)

    result = critique(critic_request(), client(server), cfg=PRICED)

    assert result.scores == []
    assert result.calls == 1
    assert result.failure is not None
    assert result.failure.startswith("the LLM request failed:")


def test_the_estimate_counts_text_and_image_tokens() -> None:
    request = critic_request(n_frames=3)

    estimate = estimate_critic_cost(request, PRICED)

    # Each 90x160 frame: ceil(90 / 28) x ceil(160 / 28) = 4 x 6 patches.
    text = tokens_of(system_prompt()) + tokens_of(user_prompt(request))
    assert estimate.input_tokens == text + 3 * 24
    assert estimate.max_calls == MAX_CALLS
    assert estimate.usd == (estimate.input_tokens + estimate.output_tokens) * 2e-6


def test_reply_scores_rejects_bad_replies() -> None:
    twice = json.loads(scores_reply())
    twice["scores"].append(twice["scores"][0])
    unknown = json.loads(scores_reply())
    unknown["scores"][0]["check"] = "vibes"

    assert reply_scores("not json")[0] is None
    duplicate_scores, problems = reply_scores(json.dumps(twice))
    assert duplicate_scores is None
    assert any("more than once: preset_faithfulness" in p for p in problems)
    assert reply_scores(json.dumps(unknown))[0] is None
    scores, none = reply_scores("```json\n" + scores_reply() + "\n```")
    assert none == [] and scores is not None and len(scores) == len(CHECKS)
