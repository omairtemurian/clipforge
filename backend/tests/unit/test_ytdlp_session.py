"""The yt-dlp session params: browser cookies, cookies file, n-challenge
solver, and the message of failures that need a signed-in session."""

from pathlib import Path

import pytest
from clipforge import config
from clipforge.config import Settings
from clipforge.pipeline import ytdlp_session
from clipforge.pipeline.download import ytdlp_options
from clipforge.pipeline.ytdlp_session import (
    SIGN_IN_MESSAGE,
    failure_message,
    parse_browser,
    session_options,
)

COOKIE_KEYS = {"cookiesfrombrowser", "cookiefile"}
AGE_GATE = (
    "[youtube] jLbst85USN8: Sign in to confirm your age. This video may be "
    "inappropriate for some users. Use --cookies-from-browser or --cookies "
    "for the authentication."
)


def cfg(browser: str = "", cookies_file: str = "") -> Settings:
    """The current settings with the given yt-dlp cookie settings."""
    return config.settings.model_copy(
        update={
            "ytdlp_cookies_from_browser": browser,
            "ytdlp_cookies_file": cookies_file,
        }
    )


@pytest.fixture
def node(monkeypatch: pytest.MonkeyPatch) -> str:
    """Make node look installed at a fixed path."""
    path = "/usr/local/bin/node"
    monkeypatch.setattr(
        ytdlp_session.shutil, "which", lambda name: path if name == "node" else None
    )
    return path


def test_unset_cookies_add_no_cookie_options(node: str) -> None:
    assert not COOKIE_KEYS & session_options(cfg()).keys()


def test_browser_gives_the_cookiesfrombrowser_tuple(node: str) -> None:
    options = session_options(cfg("chrome"))

    assert options["cookiesfrombrowser"] == ("chrome", None, None, None)
    assert "cookiefile" not in options


def test_browser_profile_is_passed_on(node: str) -> None:
    options = session_options(cfg(" Chrome:Profile 1 "))

    assert options["cookiesfrombrowser"] == ("chrome", "Profile 1", None, None)


def test_cookies_file_gives_cookiefile(node: str, tmp_path: Path) -> None:
    cookies = tmp_path / "cookies.txt"
    options = session_options(cfg(cookies_file=str(cookies)))

    assert options["cookiefile"] == str(cookies)
    assert "cookiesfrombrowser" not in options


def test_node_and_the_ejs_solver_are_enabled_when_node_is_on_path(node: str) -> None:
    options = session_options(cfg())

    assert options["js_runtimes"] == {"node": {"path": node}}
    assert options["remote_components"] == {"ejs:github"}


def test_without_node_no_js_runtime_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ytdlp_session.shutil, "which", lambda name: None)

    options = session_options(cfg("firefox"))

    assert "js_runtimes" not in options and "remote_components" not in options
    assert options["cookiesfrombrowser"] == ("firefox", None, None, None)


@pytest.mark.parametrize("spec", ["", "  ", ":Profile 1"])
def test_an_empty_browser_means_no_cookies(spec: str) -> None:
    assert parse_browser(spec) is None


def test_an_unknown_browser_is_rejected() -> None:
    with pytest.raises(ValueError, match="'netscape' is not a supported browser"):
        parse_browser("netscape")


def test_download_options_use_the_current_settings(
    node: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config, "settings", cfg("safari", "~/cookies.txt"))

    options = ytdlp_options(tmp_path, lambda event: None)

    assert options["cookiesfrombrowser"] == ("safari", None, None, None)
    assert options["cookiefile"] == "~/cookies.txt"
    assert options["format"] == "bv*[height<=1080]+ba/b[height<=1080]"


@pytest.mark.parametrize(
    "error",
    [AGE_GATE, "[youtube] x: Sign in to confirm you're not a bot", "use --cookies"],
)
def test_sign_in_failures_get_the_friendly_message(error: str) -> None:
    assert failure_message("download failed", error) == SIGN_IN_MESSAGE


def test_other_failures_keep_the_prefix_and_text() -> None:
    message = failure_message("download failed", "HTTP Error 404: Not Found")

    assert message == "download failed: HTTP Error 404: Not Found"
