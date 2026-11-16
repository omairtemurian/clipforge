"""The engine framework (SPEC-v2 2.3): install checks, the registry cache
and one real check per optional engine (SPEC-v2 5).

An engine that is not installed skips its test (conftest); an installed one
must work. `make check-engines` runs these.
"""

import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

import engine_probes
import pytest
from clipforge import config, engines
from clipforge.engines import Engine, InstallStatus
from clipforge.engines.checks import BinaryEngine, ModuleEngine, YamnetEngine
from clipforge.model_files import YAMNET_SHA256, yamnet_model_dir
from engine_probes import VERIFY, repo_root


@pytest.mark.parametrize(
    "marker", [pytest.param(name, marks=getattr(pytest.mark, name)) for name in VERIFY]
)
def test_installed_engine_works(marker: str) -> None:
    VERIFY[marker]()


def test_every_engine_marker_is_registered_and_in_check_engines() -> None:
    pyproject = tomllib.loads((repo_root() / "pyproject.toml").read_text())
    registered = {
        line.split(":", 1)[0]
        for line in pyproject["tool"]["pytest"]["ini_options"]["markers"]
    }
    makefile = (repo_root() / "Makefile").read_text()
    markers = {engine.marker for engine in engines.ENGINES.values()}
    assert markers == set(VERIFY)
    for name in markers:
        assert name in registered
        assert name in makefile


def heading_slugs(readme: str) -> set[str]:
    """GitHub's anchors of the README headings (lowercase, punctuation
    dropped, spaces to hyphens)."""
    slugs = set()
    for title in re.findall(r"^#+ (.+)$", readme, flags=re.MULTILINE):
        slugs.add(re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-"))
    return slugs


def test_every_engine_has_a_readme_section_for_its_anchor() -> None:
    slugs = heading_slugs((repo_root() / "README.md").read_text())
    for engine in engines.ENGINES.values():
        assert engine.doc_anchor in slugs, engine.name


def test_module_engine_reports_version_or_why_it_is_missing() -> None:
    found = ModuleEngine("t", "T", "pytest", "pytest").install_check()
    assert found.installed and found.error is None
    assert found.version is not None
    absent = ModuleEngine("t", "T", "clipforge_no_such_module", "x-pkg")
    assert absent.install_check() == InstallStatus(
        installed=False, error="Python package x-pkg is not installed"
    )


def test_binary_engine_reports_why_it_is_missing() -> None:
    assert BinaryEngine("t", "T", "sh").install_check().installed
    absent = BinaryEngine("t", "T", "clipforge-no-such-binary").install_check()
    assert absent.installed is False
    assert absent.error == "clipforge-no-such-binary is not on PATH"


def test_yamnet_engine_needs_its_model_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "settings", config.Settings(models_dir=tmp_path))
    engine = YamnetEngine("yamnet", "Y")
    status = engine.install_check()
    assert status.installed is False
    assert status.error is not None and "missing" in status.error
    directory = yamnet_model_dir(config.settings)
    directory.mkdir(parents=True)
    for name in YAMNET_SHA256:
        (directory / name).write_bytes(b"x")
    assert engine.install_check().installed is True


class FakeEngine(Engine):
    """An engine whose install state the test sets and whose checks it counts."""

    def __init__(self, installed: bool) -> None:
        super().__init__("fake", "Fake")
        self.installed = installed
        self.checks = 0

    def install_check(self) -> InstallStatus:
        self.checks += 1
        if self.installed:
            return InstallStatus(installed=True, version="1.0")
        return InstallStatus(installed=False, error="fake is not installed")


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeEngine]:
    """A registered FakeEngine; the check cache is emptied around the test."""
    engine = FakeEngine(installed=False)
    monkeypatch.setitem(engines.ENGINES, "fake", engine)
    engines.clear_cache()
    yield engine
    engines.clear_cache()


def test_checks_are_cached_until_refresh(fake: FakeEngine) -> None:
    assert engines.is_installed("fake") is False
    fake.installed = True
    assert engines.is_installed("fake") is False
    assert fake.checks == 1
    assert engines.is_installed("fake", refresh=True) is True
    assert engines.install_status("fake").version == "1.0"
    assert fake.checks == 2


def test_status_has_the_flag_the_error_and_the_anchor(fake: FakeEngine) -> None:
    status = next(s for s in engines.engine_statuses() if s.name == "fake")
    assert status.model_dump() == {
        "name": "fake",
        "label": "Fake",
        "installed": False,
        "version": None,
        "error": "fake is not installed",
        "doc_anchor": "engine-fake",
    }
    assert fake.marker == "engine_fake"


def test_unknown_engine_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        engines.get_engine("no-such-engine")


def test_skip_reason_only_for_a_not_installed_engine(
    monkeypatch: pytest.MonkeyPatch, fake: FakeEngine
) -> None:
    assert engine_probes.missing_reason("live") is None
    assert engine_probes.missing_reason("engine_fake") == "fake is not installed"
    fake.installed = True
    assert engine_probes.missing_reason("engine_fake") is None
