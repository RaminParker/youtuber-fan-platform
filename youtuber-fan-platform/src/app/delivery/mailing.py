"""The mailing lifecycle. Mailing status is written here and nowhere else.

Every transition is one conditional ``UPDATE … WHERE id = :id AND status =
:expected`` and the caller checks the row count. Zero rows means somebody else
moved the row first — the creator's stop link, a reschedule, another step — and
the caller then does nothing further. That, and not a lock, is what lets the web
process and the worker write the same row safely.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app import log
from app.db.models import Appearance, Mailing, MailingStatus
from app.jobs.schedule import compute_send_at
from app.tokens import new_token

logger = log.get_logger(__name__)


def schedule_mailing(
    session: Session,
    appearance: Appearance,
    *,
    delay_hours: int,
    min_delay_hours: int,
    now: datetime,
) -> Mailing:
    """Create the planned send for one item.

    The unique constraint on ``appearance_id`` is what makes this safe to reach
    twice: one item can never acquire a second mailing, whatever the pipeline
    does.
    """
    send_at = compute_send_at(appearance.published_at, delay_hours, now, min_delay_hours)
    mailing = Mailing(
        appearance_id=appearance.id,
        status=MailingStatus.SCHEDULED,
        send_at=send_at,
        stop_token=new_token(),
    )
    session.add(mailing)
    session.flush()
    logger.info(
        log.MAILING_SCHEDULED,
        mailing_id=mailing.id,
        appearance_id=appearance.id,
        send_at=send_at,
        delay_hours=delay_hours,
    )
    return mailing
