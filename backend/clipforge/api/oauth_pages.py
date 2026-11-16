"""The small HTML page that an OAuth callback answers in the sign-in tab
(Google Drive import, social accounts)."""

import html

from fastapi.responses import HTMLResponse


def result_page(title: str, message: str, status: int) -> HTMLResponse:
    """Return a minimal HTML page with title and message (escaped)."""
    body = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title></head>"
        "<body style='font-family:system-ui;margin:4rem auto;max-width:32rem'>"
        f"<h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>"
        "</body></html>"
    )
    return HTMLResponse(body, status_code=status)
