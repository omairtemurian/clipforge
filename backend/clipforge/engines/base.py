"""The optional-engine interface (SPEC-v2 2.3).

A heavy AI feature runs as an engine: a module that knows whether its
package, program or model is on this machine (`install_check`) and where
the README explains how to install it (`doc_anchor`). A missing engine is
reported, never raised: the UI then shows "Not installed - see setup".
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel


class InstallStatus(BaseModel):
    """What `install_check` found: whether the engine is usable, its version
    when it has one, and why it is not installed (None when it is)."""

    installed: bool
    version: str | None = None
    error: str | None = None


class EngineStatus(BaseModel):
    """One engine as `GET /api/engines` returns it: the capability flag
    (`installed`) the UI reads, and the README section for its setup."""

    name: str
    label: str
    installed: bool
    version: str | None
    error: str | None
    doc_anchor: str


class Engine(ABC):
    """An optional engine. `name` is its id (also its pytest marker,
    `engine_<name>`) and `doc_anchor` the README heading slug of its setup."""

    def __init__(self, name: str, label: str) -> None:
        self.name = name
        self.label = label

    @property
    def marker(self) -> str:
        """The pytest marker of the tests that need this engine."""
        return f"engine_{self.name}"

    @property
    def doc_anchor(self) -> str:
        """The README heading slug of the engine's install instructions."""
        return f"engine-{self.name.replace('_', '-')}"

    @abstractmethod
    def install_check(self) -> InstallStatus:
        """Say whether the engine is installed; never raise for a missing one."""

    def status(self, check: InstallStatus | None = None) -> EngineStatus:
        """The API view of the engine (runs `install_check` unless given)."""
        found = self.install_check() if check is None else check
        return EngineStatus(
            name=self.name,
            label=self.label,
            installed=found.installed,
            version=found.version,
            error=found.error,
            doc_anchor=self.doc_anchor,
        )
