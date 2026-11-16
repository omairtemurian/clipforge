"""The README's setup docs (SPEC-v2 2.3/3.10): every engine says how to
install it and how it is checked, and every publishing platform has its
developer-app setup, review notes and official doc links."""

import re
from urllib.parse import urlparse

import pytest
from clipforge import engines
from engine_probes import repo_root

PLATFORMS = {
    "YouTube": {"developers.google.com"},
    "TikTok": {"developers.tiktok.com"},
    "Instagram": {"developers.facebook.com"},
    "Facebook": {"developers.facebook.com"},
}


def sections(prefix: str) -> dict[str, str]:
    """The README's `### <prefix>...` sections: heading -> body."""
    text = (repo_root() / "README.md").read_text()
    found = re.split(r"^### (.+)$", text, flags=re.MULTILINE)
    return {
        found[i]: re.split(r"^## ", found[i + 1], flags=re.MULTILINE)[0]
        for i in range(1, len(found), 2)
        if found[i].startswith(prefix)
    }


def test_every_engine_has_install_and_install_check_steps() -> None:
    found = sections("Engine: ")
    assert len(found) == len(engines.ENGINES)
    for heading, body in found.items():
        assert "**Install" in body, heading
        assert "**Install check:**" in body, heading


@pytest.mark.parametrize("platform", PLATFORMS)
def test_every_platform_has_app_setup_review_notes_and_official_links(
    platform: str,
) -> None:
    body = sections(f"{platform} publishing")[f"{platform} publishing"]
    assert "**Developer app setup.**" in body
    assert "**Review notes.**" in body
    hosts = {
        urlparse(url).hostname for url in re.findall(r"\]\((https://[^)]+)\)", body)
    }
    assert PLATFORMS[platform] <= hosts


def test_the_readme_documents_campaigns_and_autopilot() -> None:
    text = (repo_root() / "README.md").read_text()
    assert "### Campaigns and autopilot" in text
    assert "(#campaigns-and-autopilot)" in text
    assert "human_only" in text
