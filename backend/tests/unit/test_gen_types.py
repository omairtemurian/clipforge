"""scripts/gen_types.py: frontend/src/api/types.ts is generated and not stale."""

import inspect
import subprocess
import sys
from pathlib import Path

import pytest
from clipforge import models
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "gen_types.py"
TYPES = ROOT / "frontend" / "src" / "api" / "types.ts"


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    """Run gen_types.py in a subprocess, as `make check` does."""
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Generate types.ts into a temp file once."""
    target = tmp_path_factory.mktemp("types") / "types.ts"
    done = run_script("--output", str(target))
    assert done.returncode == 0, done.stderr
    return target


def test_generated_matches_committed_file(generated: Path) -> None:
    assert generated.read_text() == TYPES.read_text()


def test_header_says_generated() -> None:
    assert "GENERATED FILE - DO NOT EDIT BY HAND" in TYPES.read_text().splitlines()[2]


def test_check_passes_when_fresh(generated: Path) -> None:
    done = run_script("--check", "--output", str(generated))
    assert done.returncode == 0, done.stderr


def test_check_fails_when_stale(generated: Path, tmp_path: Path) -> None:
    stale = tmp_path / "types.ts"
    stale.write_text(
        generated.read_text().replace(
            "export interface Word {", "export interface Word {\n  gone: number;"
        )
    )
    done = run_script("--check", "--output", str(stale))
    assert done.returncode == 1
    assert "is stale" in done.stderr
    assert "gen_types.py" in done.stderr
    assert "gone" in stale.read_text()  # --check writes nothing


def test_check_fails_when_file_is_missing(tmp_path: Path) -> None:
    done = run_script("--check", "--output", str(tmp_path / "missing.ts"))
    assert done.returncode == 1


def test_every_model_of_models_py_is_typed() -> None:
    text = TYPES.read_text()
    names = [
        name
        for name, cls in inspect.getmembers(models, inspect.isclass)
        if issubclass(cls, BaseModel)
        and cls.__module__ == models.__name__
        and "[" not in name
    ]
    assert names
    for name in names:
        assert f"export interface {name} " in text or f"export type {name} " in text


def test_responses_have_required_fields_and_requests_optional() -> None:
    text = TYPES.read_text()
    clip = text.split("export interface Clip {")[1].split("}")[0]
    assert "  layout:" in clip
    assert "output_path: string | null;" in clip
    patch = text.split("export interface ClipPatch {")[1].split("}")[0]
    assert "  start?: number | null;" in patch
