"""Tests of the test mode of `clipforge run`: both switches or none."""

from pathlib import Path

import pytest
from clipforge import llm
from clipforge.testmode import ENV_VAR, RecordedInputs, RecordedLLM, recorded_inputs
from fakes import FIXTURES, LLM_RESPONSE

ON = {ENV_VAR: "1"}


def test_test_mode_is_off_without_both_switches() -> None:
    assert recorded_inputs(None, {}) is None
    assert recorded_inputs(None, {ENV_VAR: "0"}) is None


def test_test_mode_uses_the_recorded_files_of_the_fixtures_dir() -> None:
    assert recorded_inputs(FIXTURES, ON) == RecordedInputs(
        transcript=FIXTURES / "transcript.json",
        llm_response=FIXTURES / "llm_response.json",
    )


def test_test_mode_reads_the_process_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENV_VAR, "1")
    assert recorded_inputs(FIXTURES) is not None
    monkeypatch.delenv(ENV_VAR)
    assert recorded_inputs(None) is None


@pytest.mark.parametrize(
    ("fixtures_dir", "environ", "error"),
    [
        (None, ON, "CLIPFORGE_TEST_MODE=1 needs --fixtures-dir"),
        (FIXTURES, {}, "--fixtures-dir needs CLIPFORGE_TEST_MODE=1"),
        (FIXTURES, {ENV_VAR: "true"}, "--fixtures-dir needs CLIPFORGE_TEST_MODE=1"),
    ],
)
def test_one_switch_alone_is_an_error(
    fixtures_dir: Path | None, environ: dict[str, str], error: str
) -> None:
    with pytest.raises(ValueError) as excinfo:
        recorded_inputs(fixtures_dir, environ)
    assert str(excinfo.value) == error


def test_test_mode_needs_both_recorded_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="transcript.json, which is not a file"):
        recorded_inputs(tmp_path, ON)

    (tmp_path / "transcript.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="llm_response.json, which is not a file"):
        recorded_inputs(tmp_path, ON)


def test_recorded_llm_answers_every_prompt_with_the_file() -> None:
    recorded = RecordedLLM(LLM_RESPONSE)
    reply = LLM_RESPONSE.read_text(encoding="utf-8")

    assert recorded.complete_json("system", "user 1") == reply
    assert recorded.complete_json("other", "user 2") == reply
    assert isinstance(recorded, llm.LLMClient)
