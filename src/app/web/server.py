"""The FastAPI application and its middleware."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from app import log
from app.config import Settings, get_settings
from app.jinja import TEMPLATE_DIR
from app.web.limits import limiter
from app.web.routes import creator, fan, public, webhooks

STATIC_DIR = TEMPLATE_DIR.parent / "static"
REQUEST_ID_HEADER = "X-Request-ID"

logger = log.get_logger(__name__)


def handle_rate_limited(request: Request, exc: Exception) -> Response:
    """Answer a throttled request plainly, without leaking what was throttled."""
    logger.warning("web.rate_limited", path=request.url.path)
    return JSONResponse({"detail": "Zu viele Anfragen. Bitte kurz warten."}, status_code=429)


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
