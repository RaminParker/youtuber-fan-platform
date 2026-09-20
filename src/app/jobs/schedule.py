"""The scheduling arithmetic. No database, no clock of its own, no side effects.

``now`` is always a parameter. That is what lets the tests drive the whole
pipeline with a stepped clock instead of waiting seven real days.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from app.config import ScheduleSettings
from app.db.models import MailingStatus

#: How often a step may fail temporarily before its row is given up on.
MAX_ATTEMPTS = 10

#: The ladder: 5, 10, 20, 40, 80, 160, 320 minutes, then 6 h, 6 h. Nine waits,
#: about 23 hours in total — comfortably inside the 48-hour minimum delay, so a
#: day of trouble never costs a mail.
FIRST_RETRY = timedelta(minutes=5)
RETRY_CAP = timedelta(hours=6)

#: What a row waits for when the condition is not an error but a fact of the
#: world: a premiere that has not started, a daily cost cap that has not reset.
#: These do not count as attempts and never lead to `failed`.
WAIT_FOR_THE_WORLD = timedelta(hours=6)


def compute_send_at(
    published_at: datetime, delay_hours: int, now: datetime, min_delay_hours: int
) -> datetime:
    """Return when the summary mail for an item should go out.

    The 48-hour minimum counts from the moment the item became public, which at
    scheduling time is never later than ``now`` — so the floor is ``now`` plus
    the minimum, not a separate lead value. Two cases make this matter: a back
    catalogue video published years ago, and a creator who shortens the delay
    below the time that has already passed.

    Parameters
    ----------
    published_at
        When the item became publicly available.
    delay_hours
        The creator's chosen delay.
    now
        The current time.
    min_delay_hours
        The floor the product guarantees, whatever the creator chose.

    Returns
    -------
    datetime
        Never earlier than ``now + min_delay_hours``.
    """
    wanted = published_at + timedelta(hours=delay_hours)
    floor = now + timedelta(hours=min_delay_hours)
    return max(wanted, floor)


def retry_at(attempts: int, now: datetime) -> datetime:
    """Return when a step that just failed temporarily should be tried again.

    Parameters
    ----------
    attempts
        The number of attempts *including* the one that just failed.
    now
        The current time.
    """
    exponent = max(0, attempts - 1)
    # Compute in seconds and cap before it can overflow on a large attempt count.
    wait = min(FIRST_RETRY * (2**exponent), RETRY_CAP) if exponent < 20 else RETRY_CAP
    return now + wait


def has_attempts_left(attempts: int) -> bool:
    """Whether a row may be tried again, or has to be given up on."""
    return attempts < MAX_ATTEMPTS


#: The three mailing steps, by name. The worker maps each to its function.
PREPARE_SENTIMENT = "prepare_sentiment"
SEND_PREVIEW = "send_preview"
SEND = "send"


class MailingTimes(Protocol):
    """What the schedule needs to know about a mailing — an ORM row fits."""

    status: str
    send_at: datetime
    preview_sent_at: datetime | None


def preview_deadline(send_at: datetime, schedule: ScheduleSettings) -> datetime:
    """Return when the creator's preview is due: one stop window before the send."""
    return send_at - timedelta(minutes=schedule.stop_window_minutes)


def next_mailing_step(
    mailing: MailingTimes, now: datetime, schedule: ScheduleSettings
) -> str | None:
    """Return which step a mailing needs at ``now``, or ``None`` if it can wait.

    The send needs two things, not one: its time has come, and the preview has
    been out for a full stop window. The second is what protects the creator
    when the worker was down across the send time — the late preview still gets
    its whole hour.
    """
    if mailing.status == MailingStatus.SCHEDULED:
        due = mailing.send_at - timedelta(hours=schedule.sentiment_lead_hours)
        return PREPARE_SENTIMENT if now >= due else None
    if mailing.status == MailingStatus.SENTIMENT_READY:
        return SEND_PREVIEW if now >= preview_deadline(mailing.send_at, schedule) else None
    if mailing.status == MailingStatus.PREVIEW_SENT:
        window_over = mailing.preview_sent_at + timedelta(minutes=schedule.stop_window_minutes)
        return SEND if now >= mailing.send_at and now >= window_over else None
    if mailing.status == MailingStatus.SENDING:
        return SEND
    return None


def postponed_send_at(
    send_at: datetime, published_at: datetime, schedule: ScheduleSettings
) -> datetime | None:
    """Return where "verschieben" moves a send, or ``None`` past the cap.

    The cap is the maximum delay, counted from publication: a summary a month
    after the video is no longer a "Nachklang".
    """
    cap = published_at + timedelta(hours=schedule.max_delay_hours)
    moved = min(send_at + timedelta(hours=schedule.postpone_hours), cap)
    return moved if moved > send_at else None
