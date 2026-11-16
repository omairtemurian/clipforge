"""Tests for reply_json: the JSON text of a model reply without the Markdown
code fence that Claude models put around it (STEERING 8b), as curate and
regenerate-text read it."""

import json

import pytest
from clipforge import clip_text
from clipforge.llm import reply_json
from clipforge.models import CandidateList
from clipforge.pipeline.curate import Window, ask_window, parse_reply
from clipforge.pipeline.enrich import PromptLine
from fakes import LLM_RESPONSE, FakeLLMClient

REPLY = LLM_RESPONSE.read_text(encoding="utf-8").strip()
CLIPS = CandidateList.model_validate_json(REPLY).clips
WINDOW = Window(0, 600, [PromptLine(0.5, "[00:00.5-00:01.4] S0: Hi everyone.")])
# Recorded from claude-sonnet-5.5 on Copilot's /chat/completions with
# response_format json_object (Hermes probe, 2026-10-31).
CLAUDE_REPLY = '```json\n{"ok":true}\n```'
TEXT = {"title": "A title", "description": "About it.", "hashtags": ["a", "b", "c"]}


@pytest.mark.parametrize(
    "reply",
    [
        '{"ok":true}',
        CLAUDE_REPLY,
        '```\n{"ok":true}\n```',
        '```JSON\n{"ok":true}```',
        '  ```json5 \n{"ok":true}\n```\n\n',
        '```json{"ok":true}```',
    ],
    ids=["unfenced", "claude", "no-tag", "tag-case", "blanks", "one-line"],
)
def test_reply_json_strips_one_surrounding_fence(reply: str) -> None:
    assert json.loads(reply_json(reply)) == {"ok": True}


@pytest.mark.parametrize(
    "reply",
    [
        'Here you go:\n```json\n{"ok":true}\n```',
        '```json\n{"ok":true}\n```\nAnything else?',
    ],
    ids=["text-before", "text-after"],
)
def test_reply_json_keeps_text_around_a_fence(reply: str) -> None:
    assert reply_json(reply) == reply


def test_curate_reads_a_fenced_claude_reply() -> None:
    assert parse_reply(f"```json\n{REPLY}\n```") == CLIPS


def test_curate_retries_a_reply_with_text_before_its_fence() -> None:
    fake = FakeLLMClient(f"Here are the clips:\n```json\n{REPLY}\n```", REPLY)

    assert ask_window(fake, "system", WINDOW) == CLIPS

    assert len(fake.calls) == 2
    assert "Your previous reply for this transcript was not valid" in fake.calls[1][1]


@pytest.mark.parametrize(
    "reply",
    [json.dumps(TEXT), f"```json\n{json.dumps(TEXT)}\n```"],
    ids=["unfenced", "fenced"],
)
def test_regenerate_text_reads_fenced_and_unfenced_replies(reply: str) -> None:
    text = clip_text.parse_reply(reply)

    assert text.model_dump() == TEXT
