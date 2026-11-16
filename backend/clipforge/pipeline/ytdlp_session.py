"""The signed-in session that yt-dlp uses for a page: the owner's own browser
cookies (or a cookies.txt file) and the JavaScript runtime that solves
YouTube's n challenge. Nothing here stores a password: yt-dlp reads the
cookies of a browser the owner is logged into.
"""

import shutil
from typing import TYPE_CHECKING, Final, Literal, cast

from yt_dlp.cookies import SUPPORTED_BROWSERS

from clipforge.config import Settings

if TYPE_CHECKING:
    from yt_dlp import _YoutubeDLOptions

SIGN_IN_MESSAGE = (
    "This video needs a signed-in YouTube session. Set 'Browser cookies' in "
    "Settings (e.g. chrome) and retry."
)
# Text of yt-dlp errors that a signed-in session would avoid.
SIGN_IN_MARKERS = ("Sign in to confirm", "--cookies")
# yt-dlp fetches the n-challenge solver script from yt-dlp-ejs on GitHub.
JS_RUNTIME = "node"
REMOTE_COMPONENT: Final[Literal["ejs:github"]] = "ejs:github"

BrowserSpec = tuple[str, str | None, None, None]


def parse_browser(spec: str) -> BrowserSpec | None:
    """Return the cookiesfrombrowser tuple of spec, "browser[:profile]".

    The tuple is (browser, profile or None, keyring None, container None).
    An empty spec gives None. Raises ValueError if the browser is not one
    that yt-dlp reads cookies from.
    """
    name, _, profile = spec.strip().partition(":")
    browser = name.strip().lower()
    if not browser:
        return None
    if browser not in SUPPORTED_BROWSERS:
        known = ", ".join(sorted(SUPPORTED_BROWSERS))
        raise ValueError(f"{browser!r} is not a supported browser ({known})")
    return (browser, profile.strip() or None, None, None)


def session_options(cfg: Settings) -> "_YoutubeDLOptions":
    """Return the YoutubeDL params for the cookies and JavaScript runtime.

    cookiesfrombrowser and cookiefile are set only when cfg sets
    ytdlp_cookies_from_browser or ytdlp_cookies_file. Node (when it is on
    PATH) is enabled with the ejs:github solver, as YouTube downloads need
    the n challenge solved.
    """
    options: _YoutubeDLOptions = {}
    browser = parse_browser(cfg.ytdlp_cookies_from_browser)
    if browser is not None:
        # The stubs say tuple[str, ...]; yt-dlp documents None for unset parts.
        options["cookiesfrombrowser"] = cast("tuple[str, ...]", browser)
    cookies_file = cfg.ytdlp_cookies_file.strip()
    if cookies_file:
        options["cookiefile"] = cookies_file
    node = shutil.which(JS_RUNTIME)
    if node is not None:
        options["js_runtimes"] = {JS_RUNTIME: {"path": node}}
        options["remote_components"] = {REMOTE_COMPONENT}
    return options


def failure_message(prefix: str, error: str) -> str:
    """Return the StepError message of a yt-dlp failure with text error.

    A failure that a signed-in session would avoid gets SIGN_IN_MESSAGE,
    which the UI shows as it is; any other is "<prefix>: <error>".
    """
    if any(marker in error for marker in SIGN_IN_MARKERS):
        return SIGN_IN_MESSAGE
    return f"{prefix}: {error}"
