"""The LLM Director's cost (SPEC-v3 3.5/1.6, TASK-221): the estimate shown
before a run, the USD price of metered tokens and the monthly cap that
blocks a run with a clear error."""

from datetime import UTC, datetime

import pytest
from clipforge import usage
from clipforge.asset_rows import UsageRecordRow
from clipforge.llm import OpenAICompatClient
from clipforge.proedit.config import ProEditConfig
from clipforge.proedit.director_cost import (
    MAX_CALLS,
    PROEDIT,
    CostEstimate,
    ProEditCapExceeded,
    check_monthly_cap,
    estimate_cost,
    month_spend_usd,
)
from clipforge.proedit.director_llm import director_plan
from fakes import FakeLLMClient, FakeLLMServer, openai_reply
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session, select
from test_llm_director import VALID, request

NOW = datetime(2026, 11, 4, 12, tzinfo=UTC)
CAPPED = ProEditConfig(monthly_cap_usd=1.0, usd_per_million_tokens=2.0)


def test_the_estimate_counts_four_characters_per_token() -> None:
    estimate = estimate_cost("s" * 4000, "u" * 2000, "r" * 400, CAPPED)

    assert (estimate.input_tokens, estimate.output_tokens) == (1500, 100)
    assert (estimate.tokens, estimate.max_calls) == (1600, MAX_CALLS)
    assert estimate.usd == pytest.approx(0.0032)
    assert estimate.max_usd == pytest.approx(0.0096)
    assert estimate.text() == (
        "About 1,600 LLM tokens ($0.0032), at most 4,800 ($0.0096) if the "
        "Director must retry."
    )


def test_without_a_price_the_estimate_shows_tokens_only() -> None:
    estimate = estimate_cost("s" * 400, "u" * 400, "r" * 400, ProEditConfig())

    assert estimate.usd is None and estimate.max_usd is None
    assert estimate.text() == (
        "About 300 LLM tokens, at most 900 if the Director must retry "
        "(no price set: proedit.usd_per_million_tokens)."
    )


def test_a_run_reports_its_estimate() -> None:
    result = director_plan(request(), FakeLLMClient(VALID), cfg=CAPPED)

    assert result.estimate is not None
    assert result.estimate.input_tokens > 1000
    assert result.estimate.output_tokens > 100
    assert result.estimate.usd is not None


def test_a_cap_needs_a_price_and_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="usd_per_million_tokens"):
        ProEditConfig(monthly_cap_usd=5.0)
    with pytest.raises(ValidationError):
        ProEditConfig(monthly_cap_usd=0.0, usd_per_million_tokens=1.0)
    assert ProEditConfig().monthly_cap_usd is None


def test_the_cap_blocks_a_run_with_a_clear_error(engine: Engine) -> None:
    usage.record(engine, PROEDIT, 495_000, cost_usd=0.99, at=NOW)
    october = datetime(2026, 10, 9, tzinfo=UTC)
    usage.record(engine, PROEDIT, 1_000_000, cost_usd=5.0, at=october)
    estimate = CostEstimate(input_tokens=900, output_tokens=100, max_calls=3, usd=0.02)

    assert month_spend_usd(engine, NOW) == pytest.approx(0.99)
    with pytest.raises(ProEditCapExceeded) as error:
        check_monthly_cap(engine, CAPPED, estimate, NOW)
    assert str(error.value) == (
        "The Pro Edit monthly cap of $1.00 is reached: $0.99 spent in 2026-11 "
        "and the Director needs about $0.02 more. Raise or remove "
        "proedit.monthly_cap_usd in config.yaml to run it."
    )
    assert isinstance(error.value, usage.UsageCapExceeded)
    check_monthly_cap(engine, ProEditConfig(usd_per_million_tokens=2.0), estimate)


def test_a_capped_director_makes_no_call_and_falls_back(engine: Engine) -> None:
    usage.record(engine, PROEDIT, 500_000, cost_usd=1.0, at=NOW)
    llm = FakeLLMClient(VALID)

    result = director_plan(request(), llm, engine=engine, cfg=CAPPED, now=NOW)

    assert llm.calls == [] and result.calls == 0
    assert result.plan.created_by == "rule_director"
    assert result.fallback is not None
    assert result.fallback.startswith("The Pro Edit monthly cap of $1.00 is reached")
    assert result.cost_usd is None


def test_recording_defaults_to_unpriced_llm_tokens(engine: Engine) -> None:
    server = FakeLLMServer(json=openai_reply("{}", tokens=(30, 10)))
    tally: list[int] = []
    llm = OpenAICompatClient(
        "https://llm.test/v1", "k", "m", transport=server.transport
    )
    with usage.recording(engine, None):
        llm.complete_json("s", "u")
    with usage.recording(engine, None, kind=PROEDIT, usd_per_token=1e-6, tally=tally):
        llm.complete_json("s", "u")

    with Session(engine) as session:
        rows = session.exec(select(UsageRecordRow)).all()
    assert [(r.kind, r.units, r.cost_usd) for r in rows] == [
        (usage.LLM_TOKENS, 40, None),
        (PROEDIT, 40, pytest.approx(4e-5)),
    ]
    assert tally == [40]
