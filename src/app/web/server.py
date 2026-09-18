"""The FastAPI application and its middleware."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.body_limit import RequestBodyLimitMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app import log
from app.config import Settings, get_settings
from app.jinja import TEMPLATE_DIR, render_partial
from app.web.limits import limiter
from app.web.pages import error_page, is_htmx, not_found
from app.web.routes import creator, fan, public, webhooks

STATIC_DIR = TEMPLATE_DIR.parent / "static"
REQUEST_ID_HEADER = "X-Request-ID"

#: Every request this app accepts — a form, a webhook — is a few kilobytes.
#: Without a cap, a handful of large bodies exhaust the web instance's memory.
MAX_BODY_BYTES = 64 * 1024

#: No URL this app hands out contains a control character. PostgreSQL rejects
#: a NUL in a string parameter, so without this check a crafted link is a 500.
CONTROL_CHARACTERS = frozenset(map(chr, [*range(32), 127]))

logger = log.get_logger(__name__)


RATE_LIMITED = "Gerade kommen sehr viele Anfragen aus deinem Netz. Bitte versuch es in einer Minute noch einmal."


def handle_rate_limited(request: Request, exc: Exception) -> Response:
    """Answer a throttled request in words, without leaking what was throttled.

    A page for a form post, a fragment for htmx — the sign-up page tells htmx
    to swap a 429 in, so a throttled click is not simply ignored.
    """
    logger.warning(log.WEB_RATE_LIMITED, path=request.url.path)
    if is_htmx(request):
        return HTMLResponse(render_partial("rate_limited", message=RATE_LIMITED), status_code=429)
    return error_page("Kurz durchatmen", RATE_LIMITED, 429)


async def handle_control_characters(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Answer a path with control characters as the unknown link it is."""
    if CONTROL_CHARACTERS.isdisjoint(request.url.path):
        return await call_next(request)
    logger.warning(log.WEB_HOSTILE_PATH)
    return not_found()


async def handle_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Give every request an id and bind it to all of its log lines.

    anyio copies the context into the threadpool, so the sync ``def`` endpoints
    see the binding too.
    """
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
    log.clear_context()
    log.bind(request_id=request_id, path=request.url.path)
    try:
        response = await call_next(request)
    finally:
        log.clear_context()
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Parameters
    ----------
    settings
        Overrides the process-wide settings. Only tests pass this.
    """
    settings = settings or get_settings()
    log.configure_logging(settings)

    app = FastAPI(title=settings.product.name, docs_url=None, redoc_url=None, openapi_url=None)
    # Added first, so it sits innermost, right above the routes: the function
    # middlewares below read the body in a task of their own, and a refusal
    # raised there would arrive wrapped in an ExceptionGroup, as a 500.
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=MAX_BODY_BYTES)
    app.middleware("http")(handle_control_characters)
    app.middleware("http")(handle_request_id)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secrets.secret_key,
        max_age=settings.email.session_hours * 3600,
        https_only=settings.base_url.startswith("https://"),
        same_site="lax",
    )
    # In-memory, and that is correct here: one web process, and a limit that
    # forgets itself on deploy is no loss.
    # One limiter for the whole app; the routes decorate themselves with it.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, handle_rate_limited)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.include_router(public.router)
    app.include_router(fan.router)
    app.include_router(creator.router)
    app.include_router(webhooks.router)

    return app
