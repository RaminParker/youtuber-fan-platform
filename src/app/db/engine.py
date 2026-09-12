"""The engine, the session factory and the one context manager that uses them.

Sync SQLAlchemy on purpose (plan §4): FastAPI runs ``def`` endpoints in a
threadpool, the worker is a single sequential loop, and async would buy nothing
here but two colours of function.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

#: Well below the 100 connections the smallest managed Postgres plan allows,
#: with room for the web process, the worker and a migration running at once.
POOL_SIZE = 5
MAX_OVERFLOW = 5

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the process-wide engine, created on first use."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().secrets.database_url,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_pre_ping=True,  # a managed database drops idle connections
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory, created on first use."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a session, commit on success, roll back on failure, always close.

    Every step and every request body runs inside exactly one of these, which is
    what makes "a crash resumes at the next loop" true.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_engine() -> None:
    """Drop the cached engine and factory.

    Only for tests, which change ``DATABASE_URL`` between cases.
    """
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
