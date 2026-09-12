"""Structured logging. Named ``log`` and not ``logging``: that would shadow the stdlib.

Configure once per process (web, worker, CLI) *before* the first logger is used,
then bind context and log events by name. The event names below are the
authority — ``docs/ARCHITECTURE.md`` describes only the naming scheme, so there
is one place to grep.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import structlog

from app.config import Settings

# --- Event vocabulary (§12) -------------------------------------------------
# Scheme: "<subject>.<what happened>", past tense, lower case.

ITEM_DETECTED = "item.detected"
ITEM_SKIPPED = "item.skipped"
ITEM_FAILED = "item.failed"

TRANSCRIPT_FETCHED = "transcript.fetched"
TRANSCRIPT_UNAVAILABLE = "transcript.unavailable"

LLM_CALL = "llm.call"
LLM_COST_CAP_HIT = "llm.cost_cap_hit"

MAILING_SCHEDULED = "mailing.scheduled"
MAILING_SENTIMENT_READY = "mailing.sentiment_ready"
MAILING_SENTIMENT_SKIPPED = "mailing.sentiment_skipped"
MAILING_PREVIEW_SENT = "mailing.preview_sent"
MAILING_BATCH_SENT = "mailing.batch_sent"
MAILING_SENT = "mailing.sent"
MAILING_STOPPED = "mailing.stopped"
MAILING_POSTPONED = "mailing.postponed"
MAILING_RESCHEDULED = "mailing.rescheduled"
MAILING_CANCELLED = "mailing.cancelled"
MAILING_FAILED = "mailing.failed"
MAILING_TRANSITION_LOST = "mailing.transition_lost"

SUBSCRIPTION_CREATED = "subscription.created"
SUBSCRIPTION_CONFIRMED = "subscription.confirmed"
SUBSCRIPTION_UNSUBSCRIBED = "subscription.unsubscribed"
SUBSCRIBER_BLOCKED = "subscriber.blocked"

WEBHOOK_RESEND = "webhook.resend"
FEED_POLLED = "feed.polled"
WORKER_TICK = "worker.tick"
STEP_RETRY = "step.retry"
QUOTA_YOUTUBE = "quota.youtube"

# --- Configuration ----------------------------------------------------------

_SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.dict_tracebacks,
]

# Libraries that talk too much at their own default level.
_STDLIB_LEVELS = {
    "sqlalchemy.engine": logging.WARNING,
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
}

# uvicorn installs its own handlers and switches propagation off, so its lines
# would keep their own shape next to ours. Take the handlers away and let the
# records reach the root logger like everyone else's.
_HAND_BACK_TO_ROOT = ("uvicorn", "uvicorn.error", "uvicorn.access")


def _renderer(settings: Settings) -> Any:
    """Pick the output format.

    The setting alone decides JSON versus console; the TTY only decides colour,
    so a redirected console log is still readable.
    """
    if settings.logging.json_format:
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())


def _handlers(settings: Settings, formatter: logging.Formatter) -> list[logging.Handler]:
    """Build the handlers: always stderr, plus a rotating file when one is configured."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if settings.logging.file:
        path = Path(settings.logging.file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(path, maxBytes=10_000_000, backupCount=5)
        )
    for handler in handlers:
        handler.setFormatter(formatter)
    return handlers


def configure_logging(settings: Settings) -> None:
    """Set up structlog and route the stdlib loggers through the same renderer.

    Call once, at process start, before anything logs — otherwise uvicorn and
    SQLAlchemy keep their own line format and the log has two shapes.

    Parameters
    ----------
    settings
        Supplies level, format and the optional log file.
    """
    structlog.configure(
        processors=[*_SHARED_PROCESSORS, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=_SHARED_PROCESSORS,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _renderer(settings),
        ],
    )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    for handler in _handlers(settings, formatter):
        root.addHandler(handler)
    root.setLevel(settings.logging.level)

    for name, level in _STDLIB_LEVELS.items():
        logging.getLogger(name).setLevel(level)

    for name in _HAND_BACK_TO_ROOT:
        library_logger = logging.getLogger(name)
        library_logger.handlers.clear()
        library_logger.propagate = True

    _configure_error_tracking(settings)


def _configure_error_tracking(settings: Settings) -> None:
    """Send exhausted retries and unexpected errors to Sentry, if a DSN is set.

    ``send_default_pii=False``: a fan's address must not leave the system
    because a step crashed near one.
    """
    if not settings.secrets.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.secrets.sentry_dsn,
        send_default_pii=False,
        environment="production" if settings.logging.json_format else "development",
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a logger. Use ``__name__`` as the name."""
    return structlog.get_logger(name)


def bind(**values: Any) -> None:
    """Bind values to every log line of this task until it is unbound.

    Used by the request-id middleware and by the worker before a step's first
    line, so that ``appearance_id`` and friends do not have to be repeated.
    """
    structlog.contextvars.bind_contextvars(**values)


def clear_context() -> None:
    """Drop everything bound. Called at the end of a request or a step."""
    structlog.contextvars.clear_contextvars()
