"""The caption marks and speaker colors of a clip (SPEC-v2 3.4) are part of
its caption_style: PATCH /api/clips/{id} saves them and the editor's preview
accepts them."""

import pytest
from apihelpers import assert_error
from clipforge.db import ClipRow
from clipforge.models import CaptionMark
from fastapi.testclient import TestClient
from seed import add_clip, add_project
from sqlalchemy import Engine
from sqlmodel import Session

STYLE = {
    "speaker_colors": {"S0": "#00FF00", "S1": "#FF00FF"},
    "word_marks": [
        {"start": 10.54, "emphasis": True, "emoji": "🔥", "source": "ai"},
        {"start": 11.7, "emphasis": False, "emoji": "", "source": "user"},
    ],
}


def test_patch_saves_word_marks_and_speaker_colors(
    client: TestClient, api_engine: Engine
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80, "Pizza")

    response = client.patch(f"/api/clips/{clip_id}", json={"caption_style": STYLE})

    assert response.status_code == 200
    with Session(api_engine) as session:
        style = session.get_one(ClipRow, clip_id).to_model().caption_style
    assert style.speaker_colors == STYLE["speaker_colors"]
    assert style.word_marks == [
        CaptionMark(start=10.54, emphasis=True, emoji="🔥", source="ai"),
        CaptionMark(start=11.7, emphasis=False, emoji="", source="user"),
    ]
    assert response.json()["caption_style"]["word_marks"][1]["source"] == "user"


@pytest.mark.parametrize(
    "style",
    [
        {"speaker_colors": {"S0": "green"}},
        {"word_marks": [{"start": 1, "emoji": "fire"}]},
        {"word_marks": [{"start": -1}]},
        {"word_marks": [{"start": 1, "source": "robot"}]},
    ],
)
def test_patch_rejects_invalid_marks_and_colors(
    client: TestClient, api_engine: Engine, style: dict[str, object]
) -> None:
    clip_id = add_clip(api_engine, add_project(api_engine), "candidate", 80, "Pizza")

    response = client.patch(f"/api/clips/{clip_id}", json={"caption_style": style})

    assert_error(response, 422, "validation_error")


def test_the_style_preview_accepts_marks_and_speaker_colors(
    client: TestClient,
) -> None:
    response = client.post("/api/caption-templates/neon/preview", json=STYLE)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
