"""The kinds of engine: a Python package, a program on PATH, the YAMNet model
files, the segmentation model and the Claude Code CLI (the Ollama vision
model is engines/vlm_ollama). Each only looks; none imports a heavy
package or runs the engine (Claude Code is asked only for its version)."""

import importlib.metadata
import importlib.util
import shutil

from clipforge import config
from clipforge.engines.base import Engine, InstallStatus
from clipforge.llm_claude_code import claude_code_version
from clipforge.llm_http import LLMError
from clipforge.model_files import missing_yamnet_files, yamnet_model_dir
from clipforge.proedit.segment import segmenter_problem


class ModuleEngine(Engine):
    """An engine that is a Python package: found with `find_spec` (so it is
    not imported); its version is that of the pip distribution."""

    def __init__(self, name: str, label: str, module: str, pip_name: str) -> None:
        super().__init__(name, label)
        self.module = module
        self.pip_name = pip_name

    def install_check(self) -> InstallStatus:
        if importlib.util.find_spec(self.module) is None:
            return InstallStatus(
                installed=False,
                error=f"Python package {self.pip_name} is not installed",
            )
        try:
            version = importlib.metadata.version(self.pip_name)
        except importlib.metadata.PackageNotFoundError:
            version = None
        return InstallStatus(installed=True, version=version)


class BinaryEngine(Engine):
    """An engine that is a command line program on PATH (no version: these
    programs have no common way to print one)."""

    def __init__(self, name: str, label: str, binary: str) -> None:
        super().__init__(name, label)
        self.binary = binary

    def install_check(self) -> InstallStatus:
        if shutil.which(self.binary) is None:
            return InstallStatus(installed=False, error=f"{self.binary} is not on PATH")
        return InstallStatus(installed=True)


class YamnetEngine(Engine):
    """The YAMNet audio-event model files in models/yamnet."""

    def install_check(self) -> InstallStatus:
        missing = missing_yamnet_files(yamnet_model_dir(config.settings))
        if missing:
            return InstallStatus(
                installed=False, error=f"YAMNet files missing: {missing}"
            )
        return InstallStatus(installed=True)


class SegmentEngine(Engine):
    """The subject cut-out of Pro Edit: the mediapipe package and its
    segmentation model in models/segment (proedit/segment.py)."""

    def install_check(self) -> InstallStatus:
        problem = segmenter_problem(config.settings)
        if problem is not None:
            return InstallStatus(installed=False, error=problem)
        return InstallStatus(installed=True)


class ClaudeCodeEngine(Engine):
    """The Claude Code CLI of the claude_code LLM provider (CLAUDE_CODE_BIN):
    installed when `<bin> --version` answers. Whether it is logged in shows
    only on a real request (Settings, Test connection)."""

    def install_check(self) -> InstallStatus:
        binary = config.settings.claude_code_bin
        try:
            return InstallStatus(installed=True, version=claude_code_version(binary))
        except LLMError:
            return InstallStatus(
                installed=False, error=f"{binary} is not installed (Claude Code)"
            )
