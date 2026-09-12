"""Rendering a page into a response. One helper, so no route repeats the plumbing."""

from __future__ import annotations

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
