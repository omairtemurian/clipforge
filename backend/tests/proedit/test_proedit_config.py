"""The proedit section of the settings (SPEC-v3 0.13): Pro Edit is available
by default; config.yaml or the PROEDIT environment variable turn it off."""

from pathlib import Path

import pytest
from clipforge.config import Settings
from clipforge.proedit.config import ProEditConfig

REPO = Path(__file__).resolve().parents[3]


def test_pro_edit_is_enabled_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    assert Settings(_env_file=None).proedit == ProEditConfig(enabled=True)


def test_the_projects_config_yaml_enables_pro_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(REPO)

    assert Settings(_env_file=None).proedit.enabled is True


def test_config_yaml_turns_pro_edit_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "config.yaml").write_text(
        "proedit:\n  enabled: false\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    assert Settings(_env_file=None).proedit.enabled is False


def test_the_environment_turns_pro_edit_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PROEDIT", '{"enabled": false}')

    assert Settings(_env_file=None).proedit.enabled is False
