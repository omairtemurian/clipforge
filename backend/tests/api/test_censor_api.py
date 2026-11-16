"""Tests of the custom censor list endpoints: GET/PUT /censor-words."""

from pathlib import Path

from apihelpers import assert_error
from clipforge.api.app import create_app
from fastapi.testclient import TestClient


def test_the_custom_list_is_empty_then_saved(data_dir: Path) -> None:
    with TestClient(create_app(run_worker=False)) as client:
        assert client.get("/api/censor-words").json() == {"words": []}

        put = client.put("/api/censor-words", json={"words": ["Heck", "dang*"]})
        got = client.get("/api/censor-words")

    assert put.status_code == 200 and put.json() == {"words": ["heck", "dang*"]}
    assert got.json() == {"words": ["heck", "dang*"]}


def test_an_invalid_list_is_422_and_a_broken_file_409(data_dir: Path) -> None:
    with TestClient(create_app(run_worker=False)) as client:
        assert_error(
            client.put("/api/censor-words", json={"words": ["two words"]}),
            422,
            "validation_error",
        )
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "censor_words.json").write_text("{")
        assert_error(client.get("/api/censor-words"), 409, "conflict")
