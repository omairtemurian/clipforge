"""The usage meter (SPEC-v2 2.4): records of compute seconds and LLM tokens,
the monthly totals and the caps."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from clipforge import jobs, usage
from clipforge.asset_rows import UsageRecordRow
from clipforge.config import Settings
from clipforge.db import JobRow
from clipforge.llm import CopilotClient, OllamaClient, OpenAICompatClient
from clipforge.models import ProcessingSettings
from clipforge.usage import (
    API_CALLS,
    COMPUTE,
    LLM_TOKENS,
    UsageCapExceeded,
    check_caps,
    job_usage,
    month_summary,
    record,
    recording,
)
from fakes import FakeLLMServer, ollama_reply, openai_reply
from seed import add_project
from sqlalchemy import Engine
from sqlmodel import Session, col, select

OCTOBER = date(2026, 10, 31)


def stored(engine: Engine, kind: str | None = None) -> list[UsageRecordRow]:
    with Session(engine) as session:
        query = select(UsageRecordRow).order_by(col(UsageRecordRow.id))
        if kind is not None:
            query = query.where(UsageRecordRow.kind == kind)
        return list(session.exec(query).all())


def openai_client(server: FakeLLMServer) -> OpenAICompatClient:
    return OpenAICompatClient(
        "https://llm.test/v1", "key", "m", transport=server.transport
    )


def test_an_openai_answer_records_its_total_tokens(engine: Engine) -> None:
    project_id = add_project(engine)
    server = FakeLLMServer(json=openai_reply("{}", tokens=(120, 30)))

    with recording(engine, project_id):
        openai_client(server).complete_json("system", "user")

    (record_,) = stored(engine)
    assert (record_.project_id, record_.kind, record_.units) == (
        project_id,
        LLM_TOKENS,
        150,
    )
    assert record_.cost_usd is None


def test_the_total_is_the_sum_when_the_server_gives_no_total(engine: Engine) -> None:
    reply = openai_reply("{}")
    reply["usage"] = {"prompt_tokens": 7, "completion_tokens": 5}
    server = FakeLLMServer(json=reply)

    with recording(engine, None):
        openai_client(server).complete_json("system", "user")

    (record_,) = stored(engine)
    assert (record_.project_id, record_.units) == (None, 12)


def test_copilot_and_ollama_answers_record_tokens(engine: Engine) -> None:
    copilot = FakeLLMServer(json=openai_reply("{}", tokens=(10, 1)))
    ollama = FakeLLMServer(json=ollama_reply("{}", tokens=(40, 2)))

    with recording(engine, None):
        CopilotClient("gpt-4.1", "token", transport=copilot.transport).complete_json(
            "s", "u"
        )
        OllamaClient(
            "http://ollama.test", "m", transport=ollama.transport
        ).complete_json("s", "u")

    assert [r.units for r in stored(engine, LLM_TOKENS)] == [11, 42]


def test_nothing_is_recorded_outside_a_context_or_without_usage(
    engine: Engine,
) -> None:
    counted = FakeLLMServer(json=openai_reply("{}", tokens=(5, 5)))
    uncounted = FakeLLMServer(json=openai_reply("{}"))

    openai_client(counted).complete_json("s", "u")
    with recording(engine, None):
        openai_client(uncounted).complete_json("s", "u")

    assert stored(engine) == []


def test_a_job_records_its_compute_seconds_even_when_it_fails(
    engine: Engine, tmp_path: Path
) -> None:
    job_id = jobs.enqueue_process(
        engine, str(tmp_path / "missing.mp4"), ProcessingSettings()
    )

    assert jobs.run_next(engine) is True

    with Session(engine) as session:
        job = session.get_one(JobRow, job_id)
    assert job.status == "failed"
    (record_,) = stored(engine, COMPUTE)
    assert record_.project_id == job.project_id
    assert 0 < record_.units < 60


def test_a_job_records_the_tokens_of_its_llm_calls_for_its_project(
    engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server = FakeLLMServer(json=openai_reply("{}", tokens=(80, 20)))
    client = openai_client(server)

    def ask_twice(engine_: Engine, job_id: int, **_: object) -> None:
        client.complete_json("s", "u")
        client.complete_json("s", "u")

    monkeypatch.setattr(jobs, "run_process_job", ask_twice)
    jobs.enqueue_process(engine, str(tmp_path / "talk.mp4"), ProcessingSettings())

    jobs.run_next(engine)

    with Session(engine) as session:
        project_id = session.exec(select(JobRow.project_id)).one()
    assert [(r.project_id, r.units) for r in stored(engine, LLM_TOKENS)] == [
        (project_id, 100),
        (project_id, 100),
    ]
    assert len(stored(engine, COMPUTE)) == 1


def test_a_metering_failure_never_fails_the_job(
    engine: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("ERROR")

    # No such project: the foreign key refuses the record.
    with job_usage(engine, 999):
        pass

    assert stored(engine) == []
    assert "could not record compute usage" in caplog.text


def test_the_summary_totals_a_month_per_kind_and_project(engine: Engine) -> None:
    first, second = add_project(engine), add_project(engine)
    october = datetime(2026, 10, 3, 12, tzinfo=UTC)
    record(engine, COMPUTE, 100, project_id=first, at=october)
    record(engine, COMPUTE, 50, project_id=first, at=october)
    record(engine, COMPUTE, 7, project_id=second, at=october)
    record(engine, LLM_TOKENS, 900, project_id=first, at=october)
    record(engine, "tts_chars", 40, cost_usd=0.25, at=october)
    record(engine, "tts_chars", 10, cost_usd=0.5, at=october)
    record(
        engine,
        COMPUTE,
        1000,
        project_id=first,
        at=datetime(2026, 9, 30, 23, 59, tzinfo=UTC),
    )
    record(
        engine, COMPUTE, 2000, project_id=first, at=datetime(2026, 11, 1, tzinfo=UTC)
    )

    summary = month_summary(engine, OCTOBER)

    assert summary.month == "2026-10"
    totals = {item.kind: item for item in summary.kinds}
    assert [item.kind for item in summary.kinds] == [
        COMPUTE,
        LLM_TOKENS,
        API_CALLS,
        "tts_chars",
    ]
    assert (totals[COMPUTE].units, totals[COMPUTE].cost_usd) == (157, None)
    assert totals[LLM_TOKENS].units == 900
    assert totals[API_CALLS].units == 0
    assert (totals["tts_chars"].units, totals["tts_chars"].cost_usd) == (50, 0.75)
    by_project = {(p.project_id, p.kind): p.units for p in summary.projects}
    assert by_project == {
        (first, COMPUTE): 150,
        (second, COMPUTE): 7,
        (first, LLM_TOKENS): 900,
        (None, "tts_chars"): 50,
    }


def test_months_roll_over_at_the_end_of_december() -> None:
    assert usage.next_month_start(date(2026, 12, 15)) == datetime(
        2027, 1, 1, tzinfo=UTC
    )
    assert usage.month_start(date(2026, 2, 28)) == datetime(2026, 2, 1, tzinfo=UTC)
    assert usage.parse_month("2026-02") == date(2026, 2, 1)
    with pytest.raises(ValueError):
        usage.parse_month("2026-13")


def test_caps_are_in_the_units_of_the_records_and_zero_means_none() -> None:
    cfg = Settings(usage_cap_compute_hours=2, usage_cap_llm_tokens=500)

    assert usage.caps_of(cfg) == {COMPUTE: 7200, LLM_TOKENS: 500}
    assert usage.caps_of(Settings()) == {}


def test_a_total_that_reaches_its_cap_is_flagged(engine: Engine) -> None:
    record(engine, COMPUTE, 3600, at=datetime(2026, 10, 1, tzinfo=UTC))
    record(engine, LLM_TOKENS, 499, at=datetime(2026, 10, 1, tzinfo=UTC))
    cfg = Settings(usage_cap_compute_hours=1, usage_cap_llm_tokens=500)

    kinds = {k.kind: k for k in month_summary(engine, OCTOBER, cfg).kinds}

    assert (kinds[COMPUTE].cap, kinds[COMPUTE].exceeded) == (3600, True)
    assert (kinds[LLM_TOKENS].cap, kinds[LLM_TOKENS].exceeded) == (500, False)
    assert (kinds[API_CALLS].cap, kinds[API_CALLS].exceeded) == (None, False)


def test_check_caps_names_the_kind_that_is_used_up(engine: Engine) -> None:
    record(engine, LLM_TOKENS, 1500, at=datetime(2026, 10, 1, tzinfo=UTC))
    cfg = Settings(usage_cap_llm_tokens=1000)

    with pytest.raises(UsageCapExceeded) as raised:
        check_caps(engine, cfg, now=datetime(2026, 10, 20, tzinfo=UTC))

    message = str(raised.value)
    assert "1,000 LLM tokens" in message and "1,500 LLM tokens" in message
    assert "2026-10" in message and "Settings" in message


def test_check_caps_only_counts_this_month_and_ignores_unset_caps(
    engine: Engine,
) -> None:
    record(engine, LLM_TOKENS, 1500, at=datetime(2026, 10, 1, tzinfo=UTC))

    check_caps(
        engine,
        Settings(usage_cap_llm_tokens=1000),
        now=datetime(2026, 11, 2, tzinfo=UTC),
    )
    check_caps(engine, Settings(), now=datetime(2026, 10, 20, tzinfo=UTC))
    check_caps(
        engine,
        Settings(usage_cap_compute_hours=1),
        now=datetime(2026, 10, 20, tzinfo=UTC),
    )


def test_a_record_defaults_to_now_in_utc(engine: Engine) -> None:
    before = datetime.now(UTC)

    record(engine, API_CALLS, 1)

    (record_,) = stored(engine)
    assert before <= record_.at <= datetime.now(UTC)
