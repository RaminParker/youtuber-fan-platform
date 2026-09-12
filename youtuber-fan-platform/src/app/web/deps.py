"""Request dependencies: a session, and who is logged in."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.engine import get_session_factory
from app.db.models import Creator

SESSION_KEY = "creator_id"


def get_session() -> Iterator[Session]:
    """Yield a database session for the length of one request."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def signed_in_creator(request: Request, session: Session = Depends(get_session)) -> Creator | None:
    """Return the signed-in creator, or ``None``."""
    creator_id = request.session.get(SESSION_KEY)
    if creator_id is None:
        return None
    return session.get(Creator, creator_id)


def current_creator(creator: Creator | None = Depends(signed_in_creator)) -> Creator:
    """Return the signed-in creator, or refuse the request."""
    if creator is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/creator/login"}
        )
    return creator
