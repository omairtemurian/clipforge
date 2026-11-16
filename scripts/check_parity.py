"""Check docs/parity.md against section 3 of the v2 spec (SPEC-v2 5).

Every bullet of SPEC-v2 section 3 needs a row in the "SPEC-v2 section 3
coverage" table of docs/parity.md, with a status and evidence (existing repo
paths in backticks). Bullets are numbered by position: `3.4.2` is the second
top-level bullet of 3.4, `3.10.1.2` the second sub-bullet of 3.10.1.

    uv run python scripts/check_parity.py       # exit 1 and list the problems

`make lint` runs it.
"""

import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "spec" / "SPEC-v2.md"
PARITY = ROOT / "docs" / "parity.md"
TABLE_HEADING = "## SPEC-v2 section 3 coverage"
STATUSES = frozenset(
    {"done", "partial", "needs platform approval", "blocked", "not planned"}
)

SECTION = re.compile(r"^(3\.\d+) ")
BULLET = re.compile(r"^(\s*)- ")
ROW_ID = re.compile(r"^\d+\.\d+\.\d+(\.\d+)?$")
PATH_TOKEN = re.compile(r"`([^`\s]+/[^`\s]*)`")


@dataclass(frozen=True)
class Row:
    """One line of the coverage table."""

    id: str
    status: str
    evidence: str


def spec_bullets(spec: str) -> dict[str, str]:
    """Return the bullets of section 3 of the spec, id -> text.

    A top-level bullet is `- ` at the start of a line, a sub-bullet is indented.
    Section 3 ends at the heading of section 4."""
    bullets: dict[str, str] = {}
    section = ""
    top = 0
    sub = 0
    for line in spec.splitlines():
        if line.startswith("4. "):
            break
        match = SECTION.match(line)
        if match:
            section, top, sub = match.group(1), 0, 0
            continue
        bullet = BULLET.match(line)
        if not section or not bullet:
            continue
        if bullet.group(1):
            sub += 1
            bullets[f"{section}.{top}.{sub}"] = line.strip()[2:]
        else:
            top += 1
            sub = 0
            bullets[f"{section}.{top}"] = line.strip()[2:]
    return bullets


def split_row(line: str) -> list[str]:
    """Split a markdown table line on unescaped pipes."""
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]


def parity_rows(parity: str) -> list[Row]:
    """Return the rows of the coverage table (the lines whose first cell is an id)."""
    rows: list[Row] = []
    inside = False
    for line in parity.splitlines():
        if line.startswith("## "):
            inside = line.strip() == TABLE_HEADING
            continue
        if not inside or not line.startswith("|"):
            continue
        cells = split_row(line)
        if len(cells) >= 4 and ROW_ID.match(cells[0]):
            rows.append(Row(cells[0], cells[2], cells[3]))
    return rows


def problems(bullets: dict[str, str], rows: Sequence[Row], root: Path) -> list[str]:
    """List what is wrong with the rows: missing, unknown or repeated ids, an
    unknown status, no evidence, an evidence path that does not exist."""
    found: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row.id in seen:
            found.append(f"{row.id}: listed twice")
        seen.add(row.id)
        if row.id not in bullets:
            found.append(f"{row.id}: not a bullet of SPEC-v2 section 3")
        if row.status not in STATUSES:
            found.append(
                f"{row.id}: status {row.status!r} is not one of {sorted(STATUSES)}"
            )
        paths = PATH_TOKEN.findall(row.evidence)
        if not paths:
            found.append(f"{row.id}: no evidence path in backticks")
        for path in paths:
            if not (root / path).exists():
                found.append(f"{row.id}: evidence {path} does not exist")
    found.extend(
        f"{id_}: no row ({text[:60]}...)"
        for id_, text in bullets.items()
        if id_ not in seen
    )
    return found


def main() -> int:
    """Check the repo's parity.md against the spec; print the problems."""
    found = problems(
        spec_bullets(SPEC.read_text()), parity_rows(PARITY.read_text()), ROOT
    )
    for line in found:
        print(line)
    if found:
        print(f"{len(found)} problem(s) in docs/parity.md", file=sys.stderr)
        return 1
    print("docs/parity.md covers every bullet of SPEC-v2 section 3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
