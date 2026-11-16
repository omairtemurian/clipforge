"""The campaign data is entered by the owner (SPEC-v2 3.18): no code of the
package names a campaign marketplace, Discord or a creator site to fetch."""

import re
from pathlib import Path

import clipforge

HOSTS = re.compile(
    r"whop\.com|whop\.io|clip-?ok|clipok|discord\.com|discord\.gg|discordapp",
    re.IGNORECASE,
)


def test_no_module_names_a_campaign_board_or_discord_host() -> None:
    package = Path(clipforge.__file__).parent

    named = [
        f"{path.relative_to(package)}: {match.group(0)}"
        for path in sorted(package.rglob("*.py"))
        if (match := HOSTS.search(path.read_text(encoding="utf-8")))
    ]

    assert named == []
