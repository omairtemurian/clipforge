"""Edit a dotenv file (.env.local) in place: the Settings page saves there.

update_env_file keeps every other line, comments included, replaces the line
of a key that is already set and appends the keys that are not. Values are
written in double quotes, in which python-dotenv (pydantic-settings' reader)
understands backslash and quote escapes.
"""

import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path

# The file holds API keys: a new one is readable by its owner only.
NEW_FILE_MODE = 0o600

KEY_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def quote(value: str) -> str:
    """Return value as a double-quoted dotenv value: "a \\"b\\"" for a "b"."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def render_env(text: str, values: Mapping[str, str]) -> str:
    """Return the dotenv text with each key of values set to its value.

    Keys are matched exactly (the file's keys are uppercase). If a key is set
    on several lines, the last one, which is the one that wins, is replaced.
    """
    lines = text.splitlines()
    last: dict[str, int] = {}
    for index, line in enumerate(lines):
        match = KEY_LINE.match(line)
        if match:
            last[match.group(1)] = index
    appended: list[str] = []
    for key, value in values.items():
        entry = f"{key}={quote(value)}"
        if key in last:
            lines[last[key]] = entry
        else:
            appended.append(entry)
    return "\n".join([*lines, *appended]) + "\n"


def write_private(path: Path, text: str) -> None:
    """Write text to path in one step (through path.tmp), keeping the file
    mode of an existing path, else NEW_FILE_MODE."""
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else NEW_FILE_MODE
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        file.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def update_env_file(path: Path, values: Mapping[str, str]) -> str | None:
    """Set the keys of values in the dotenv file at path, creating it if
    needed, and return its previous text (None if it did not exist) so that
    the caller can put it back with restore_env_file."""
    previous = path.read_text(encoding="utf-8") if path.is_file() else None
    write_private(path, render_env(previous or "", values))
    return previous


def restore_env_file(path: Path, previous: str | None) -> None:
    """Put the dotenv file at path back as update_env_file found it."""
    if previous is None:
        path.unlink(missing_ok=True)
    else:
        write_private(path, previous)
