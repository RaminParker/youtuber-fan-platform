"""Rendering a page into a response. One helper, so no route repeats the plumbing."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from app.jinja import render_page


def page(
    template: str, status_code: int = 200, headers: dict[str, str] | None = None, **context
) -> HTMLResponse:
    """Render a page template into an HTML response.

    Parameters
    ----------
    template
        Name under ``templates/pages/``, without the suffix.
    status_code
        For the pages that are also an answer: 404 for a bad link, 410 for a
        video that is gone.
    headers
        Response headers. The summary page uses it to stay out of search.
    """
    return HTMLResponse(render_page(template, **context), status_code=status_code, headers=headers)


def is_htmx(request: Request) -> bool:
    """Whether htmx sent this request and expects a fragment, not a page."""
    return request.headers.get("HX-Request") == "true"


def error_page(heading: str, message: str, code: int, **context) -> HTMLResponse:
    """Render a branded error page rather than a bare status line."""
    return page("error", status_code=code, heading=heading, message=message, **context)


def not_found() -> HTMLResponse:
    """Answer a link that leads nowhere — one wording for every route and middleware."""
    return error_page("Diese Seite gibt es nicht", "Der Link stimmt nicht.", 404)
