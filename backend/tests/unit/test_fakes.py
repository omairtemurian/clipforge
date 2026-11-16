"""FakeLLMClient, the test-only LLM (SPEC 2), and its absence from clipforge."""

import ast
import importlib.util
from pathlib import Path

import clipforge
import fakes
import pytest
from clipforge import llm
from fakes import LLM_RESPONSE, FakeLLMClient

PACKAGE = Path(clipforge.__file__).resolve().parent


def test_fake_returns_the_fixture_reply_by_default() -> None:
    fake = FakeLLMClient()
    fixture = LLM_RESPONSE.read_text(encoding="utf-8")

    assert fake.complete_json("system 1", "user 1") == fixture
    assert fake.complete_json("system 2", "user 2") == fixture
    assert fake.calls == [("system 1", "user 1"), ("system 2", "user 2")]
    assert isinstance(fake, llm.LLMClient)


def test_fake_replays_replies_in_order_then_fails(tmp_path: Path) -> None:
    reply_file = tmp_path / "reply.json"
    fake = FakeLLMClient("not json", reply_file)
    reply_file.write_text('{"clips": []}', encoding="utf-8")

    assert fake.complete_json("s", "first") == "not json"
    assert fake.complete_json("s", "second") == '{"clips": []}'
    with pytest.raises(AssertionError, match="no reply left for call 3"):
        fake.complete_json("s", "third")
    assert [user for _, user in fake.calls] == ["first", "second", "third"]


def test_fake_can_repeat_its_last_reply() -> None:
    fake = FakeLLMClient("a", "b", repeat_last=True)

    assert [fake.complete_json("s", "u") for _ in range(4)] == ["a", "b", "b", "b"]


def package_names() -> set[str]:
    """Return every name the clipforge sources define, import or look up."""
    names: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef | ast.FunctionDef):
                names.add(node.name)
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.alias):
                names.update(node.name.split("."))
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.update(node.module.split("."))
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names.add(node.value.rsplit(".", 1)[-1])
    return names


def test_fake_llm_client_is_not_importable_from_clipforge() -> None:
    names = package_names()

    assert "FakeLLMClient" not in names
    assert "fakes" not in names
    assert {"create_client", "OpenAICompatClient"} <= names
    assert importlib.util.find_spec("clipforge.fakes") is None
    assert not hasattr(llm, "FakeLLMClient")
    assert PACKAGE not in Path(fakes.__file__).resolve().parents
