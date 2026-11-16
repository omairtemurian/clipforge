"""scripts/check_parity.py: docs/parity.md covers every bullet of SPEC-v2 section 3."""

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_parity", ROOT / "scripts" / "check_parity.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SPEC = """3.1 Submit
- First bullet.
- Second bullet.
3.10 Publish
- Accounts:
  - YouTube.
  - TikTok.
- Multiple accounts.
=====
4. DATA MODEL
- Not a feature.
"""

PARITY = """# Feature parity

## SPEC-v2 section 3 coverage

| ID | Bullet | Status | Evidence |
| -- | ------ | ------ | -------- |
| 3.1.1 | First | done | `docs/parity.md` |
| 3.1.2 | Second | not planned | `docs/decisions.md` |
| 3.10.1 | Accounts | partial | `docs/parity.md` |
| 3.10.1.1 | YouTube | needs platform approval | `docs/parity.md` |
| 3.10.1.2 | TikTok | blocked | `docs/parity.md` |
| 3.10.2 | Multiple | done | `docs/parity.md` |

## Other table

| 3.9.9 | outside | done | `docs/nothing.md` |
"""


def test_the_bullets_are_numbered_by_position_and_stop_at_section_4() -> None:
    assert list(load_script().spec_bullets(SPEC)) == [
        "3.1.1",
        "3.1.2",
        "3.10.1",
        "3.10.1.1",
        "3.10.1.2",
        "3.10.2",
    ]


def test_a_complete_table_has_no_problems() -> None:
    script = load_script()
    rows = script.parity_rows(PARITY)
    assert len(rows) == 6
    assert script.problems(script.spec_bullets(SPEC), rows, ROOT / "docs" / "..") == []


def test_a_bullet_without_a_row_is_reported() -> None:
    script = load_script()
    rows = [r for r in script.parity_rows(PARITY) if r.id != "3.10.2"]
    found = script.problems(script.spec_bullets(SPEC), rows, ROOT)
    assert len(found) == 1
    assert found[0].startswith("3.10.2: no row")


def test_a_bad_status_missing_evidence_and_a_missing_path_are_reported() -> None:
    script = load_script()
    rows = [
        script.Row("3.1.1", "finished", "`docs/parity.md`"),
        script.Row("3.1.2", "done", "see the decision"),
        script.Row("3.10.1", "done", "`docs/nothing.md`"),
        script.Row("3.10.1.1", "done", "`docs/parity.md`"),
        script.Row("3.10.1.2", "done", "`docs/parity.md`"),
        script.Row("3.10.2", "done", "`docs/parity.md`"),
        script.Row("3.10.2", "done", "`docs/parity.md`"),
        script.Row("3.9.9", "done", "`docs/parity.md`"),
    ]
    found = script.problems(script.spec_bullets(SPEC), rows, ROOT)
    assert "3.1.1: status 'finished' is not one of " in "\n".join(found)
    assert "3.1.2: no evidence path in backticks" in found
    assert "3.10.1: evidence docs/nothing.md does not exist" in found
    assert "3.10.2: listed twice" in found
    assert "3.9.9: not a bullet of SPEC-v2 section 3" in found
    assert len(found) == 5


def test_the_repo_parity_file_covers_the_whole_spec() -> None:
    script = load_script()
    bullets = script.spec_bullets((ROOT / "docs" / "spec" / "SPEC-v2.md").read_text())
    rows = script.parity_rows((ROOT / "docs" / "parity.md").read_text())
    assert len(bullets) == 104
    assert script.problems(bullets, rows, ROOT) == []
