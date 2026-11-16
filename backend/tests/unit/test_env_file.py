"""env_file: editing a dotenv file that pydantic-settings reads back."""

from pathlib import Path

import pytest
from clipforge.config import Settings
from clipforge.env_file import render_env, restore_env_file, update_env_file


def test_render_replaces_the_last_line_of_a_key_and_appends_new_keys() -> None:
    text = "# c\nA=1\nexport B = 2\nA=3\n\nC=4"

    out = render_env(text, {"A": "x", "B": "y", "D": "z"})

    assert out == '# c\nA=1\nB="y"\nA="x"\n\nC=4\nD="z"\n'


def test_a_new_file_is_created() -> None:
    assert render_env("", {"A": "1"}) == 'A="1"\n'


@pytest.mark.parametrize(
    "value",
    ["plain", 'with "quotes"', "back\\slash", "Credit: {channel} #1", "it's", "a b"],
)
def test_values_read_back_as_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.chdir(tmp_path)
    for key in ("CREDIT_TEMPLATE", "LLM_MODEL"):
        monkeypatch.delenv(key, raising=False)
    update_env_file(Path(".env.local"), {"CREDIT_TEMPLATE": value, "LLM_MODEL": value})

    read = Settings()

    assert read.llm_model == value and read.credit_template == value


def test_restore_puts_the_file_back_or_removes_it(tmp_path: Path) -> None:
    path = tmp_path / ".env.local"

    created = update_env_file(path, {"A": "1"})
    assert created is None and path.exists()
    restore_env_file(path, created)
    assert not path.exists()

    path.write_text("B=2\n")
    previous = update_env_file(path, {"B": "3"})
    restore_env_file(path, previous)
    assert path.read_text() == "B=2\n"
