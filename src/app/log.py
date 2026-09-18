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
SUBSCRIPTION_ADDRESS_REJECTED = "subscription.address_rejected"
SUBSCRIPTION_CONFIRM_SENT = "subscription.confirm_sent"
SUBSCRIPTION_CONFIRM_FAILED = "subscription.confirm_failed"
SUBSCRIBER_BLOCKED = "subscriber.blocked"

CREATOR_MAGIC_LINK_SENT = "creator.magic_link_sent"
CREATOR_MAGIC_LINK_FAILED = "creator.magic_link_failed"
CREATOR_SIGNED_IN = "creator.signed_in"
CREATOR_NOTICE_FAILED = "notice.failed"

OAUTH_CONNECTED = "oauth.connected"
OAUTH_REVOKED = "oauth.revoked"

EMAIL_REFUSED = "email.refused"
EMAIL_QUOTA_EXHAUSTED = "email.quota_exhausted"

WEBHOOK_RESEND = "webhook.resend"
WEBHOOK_SECRET_UNUSABLE = "webhook.secret_unusable"

WEB_HOSTILE_PATH = "web.hostile_path"
WEB_RATE_LIMITED = "web.rate_limited"

FEED_POLLED = "feed.polled"
CLEANUP_DONE = "cleanup.done"

WORKER_STARTED = "worker.started"
WORKER_STOPPING = "worker.stopping"
WORKER_STOPPED = "worker.stopped"
WORKER_TICK = "worker.tick"
WORKER_TICK_FAILED = "worker.tick_failed"
WORKER_STEP_CRASHED = "worker.step_crashed"
WORKER_PERIODIC_FAILED = "worker.periodic_failed"
STEP_RETRY = "step.retry"
QUOTA_YOUTUBE = "quota.youtube"

# --- Configuration ----------------------------------------------------------

_SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
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


def _renderers(settings: Settings) -> list[Any]:
    """Pick the output format.

    The setting alone decides JSON versus console; the TTY only decides colour,
    so a redirected console log is still readable. Tracebacks become dicts only
    for JSON: the console renderer formats them itself and crashes on a dict.
    """
    if settings.logging.json_format:
        return [structlog.processors.dict_tracebacks, structlog.processors.JSONRenderer()]
    return [structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())]


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
            *_renderers(settings),
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

    Nothing personal or secret may leave with a report: no PII by default, no
    request bodies (sign-up forms carry addresses), and no frame locals — the
    SDK's scrubber only checks top-level names, so locals would ship the mail
    provider's key, the settings and a fan's address verbatim.
    """
    if not settings.secrets.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.secrets.sentry_dsn,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
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
