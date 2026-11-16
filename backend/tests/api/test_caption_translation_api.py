"""Tests of POST/DELETE /clips/{id}/caption-translation: a recorded LLM
reply translates a clip's captions and is saved in its caption_style, the
translation can be removed, and the errors."""

import json
from pathlib import Path
from typing import Any

from apihelpers import assert_error
from clipforge.api.app import create_app
from clipforge.llm_http import LLMError
from fakes import FakeLLMClient
from fastapi.testclient import TestClient
from seed import add_clip, add_project, add_work
from sqlalchemy import Engine

# fixtures/transcript.json in clip 10-12.5 s: two cues.
REPLY = json.dumps(
    {"cues": [{"index": 0, "text": "אמר,"}, {"index": 1, "text": "למה אנחנו"}]}
)


class Refusing:
    """An LLM that cannot be reached."""

    def complete_json(self, system: str, user: str) -> str:
        raise LLMError("refused")


def setup(client: TestClient, sample_mp4: Path | None) -> int:
    """Add a clip, with a processed source and transcript unless sample_mp4
    is None; return its id."""
    engine: Engine = client.app.state.engine  # type: ignore[attr-defined]
    project_id = add_project(engine)
    if sample_mp4 is not None:
        add_work(engine, project_id, sample_mp4)
    return add_clip(engine, project_id, "candidate", 80, "Pizza")


def translate(client: TestClient, clip_id: int, language: str = "he") -> Any:
    return client.post(
        f"/api/clips/{clip_id}/caption-translation", json={"language": language}
    )


def test_the_translation_is_saved_in_the_clips_caption_style(
    data_dir: Path, sample_mp4: Path
) -> None:
    llm = FakeLLMClient(REPLY)
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        clip_id = setup(client, sample_mp4)

        response = translate(client, clip_id)

        stored = client.get(f"/api/clips/{clip_id}").json()
    assert response.status_code == 200
    translation = response.json()["caption_style"]["translation"]
    assert translation == {
        "language": "he",
        "cues": [
            {"start": 10.09, "end": 10.5, "text": "אמר,", "speaker": "S0"},
            {"start": 11.1, "end": 12.5, "text": "למה אנחנו", "speaker": "S0"},
        ],
    }
    assert stored["caption_style"]["translation"] == translation
    assert llm.calls[0][1].startswith("Translate into: Hebrew (he)\n")


def test_delete_brings_back_the_transcripts_words_and_keeps_the_style(
    data_dir: Path, sample_mp4: Path
) -> None:
    llm = FakeLLMClient(REPLY)
    with TestClient(create_app(run_worker=False, llm=llm)) as client:
        clip_id = setup(client, sample_mp4)
        client.patch(f"/api/clips/{clip_id}", json={"caption_style": {"size": 90}})
        translate(client, clip_id)

        response = client.delete(f"/api/clips/{clip_id}/caption-translation")

    assert response.status_code == 200
    style = response.json()["caption_style"]
    assert style["translation"] is None and style["size"] == 90


def test_errors(data_dir: Path, sample_mp4: Path) -> None:
    with TestClient(create_app(run_worker=False, llm=Refusing())) as client:
        clip_id = setup(client, sample_mp4)
        bare_id = setup(client, None)

        assert_error(translate(client, clip_id), 502, "llm_error")
        assert_error(translate(client, bare_id), 409, "conflict")
        assert_error(translate(client, clip_id, "xx"), 422, "validation_error")
        assert_error(translate(client, 999), 404, "not_found")
        assert_error(
            client.delete("/api/clips/999/caption-translation"), 404, "not_found"
        )
        stored = client.get(f"/api/clips/{clip_id}").json()
    assert stored["caption_style"]["translation"] is None
