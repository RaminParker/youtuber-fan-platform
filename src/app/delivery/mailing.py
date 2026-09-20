"""The mailing lifecycle. Mailing status is written here and nowhere else.

Every transition is one conditional ``UPDATE … WHERE id = :id AND status =
:expected`` and the caller checks the row count. Zero rows means somebody else
moved the row first — the creator's stop link, a postpone, another step — and
the caller then does nothing further. That, and not a lock, is what lets the web
process and the worker write the same row safely.

"Exactly once" rests on four things together, each of which is here:

- the recipient set is a snapshot, inserted into ``deliveries`` in the same
  transaction that moves the mailing to ``sending`` (unique per recipient);
- batches are the pending deliveries ``ORDER BY id``, so a resumed run rebuilds
  the same batch, under the same idempotency key, with the same frozen payload;
- a delivery is marked sent in the transaction after its batch was accepted;
- one session-level advisory lock per mailing keeps two workers apart.
"""

from __future__ import annotations

from collections.abc import Collection, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import func, literal, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import log
from app.analysis.stored import load_analysis
from app.config import Settings
from app.creator_settings import effective_settings
from app.db.engine import get_engine
from app.db.models import (
    MAILING_STOPPABLE,
    AnalysisKind,
    Appearance,
    Creator,
    Delivery,
    Mailing,
    MailingStatus,
    Source,
    Subscriber,
    Subscription,
    SubscriptionStatus,
)
from app.delivery.email_client import BATCH_SIZE
from app.delivery.render import OutgoingEmail, render_summary_mail, snapshot_of
from app.jobs.schedule import compute_send_at, postponed_send_at
from app.services import get_services
from app.tokens import new_token

logger = log.get_logger(__name__)

#: Bookkeeping a fresh state starts without: a new state is a new run.
FRESH = {"attempts": 0, "next_attempt_at": None, "last_error": None}


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


def _transition(
    session: Session,
    mailing_id: int,
    expected: Collection[str],
    status: MailingStatus,
    *conditions,
    **values,
) -> bool:
    """Move a mailing on, if it is still where the caller last saw it.

    Returns whether this call won. A lost transition is logged and has no
    side effect: the caller must do nothing further.
    """
    moved = session.execute(
        update(Mailing)
        .where(Mailing.id == mailing_id, Mailing.status.in_(list(expected)), *conditions)
        .values(status=status, **values)
        .execution_options(synchronize_session=False)
    ).rowcount
    if moved:
        return True
    logger.info(
        log.MAILING_TRANSITION_LOST,
        mailing_id=mailing_id,
        expected=sorted(expected),
        wanted=status,
        actual=session.scalar(select(Mailing.status).where(Mailing.id == mailing_id)),
    )
    return False


def mark_sentiment_ready(session: Session, mailing_id: int, comments_used: int) -> bool:
    """``scheduled → sentiment_ready``, with or without a sentiment row."""
    won = _transition(
        session, mailing_id, {MailingStatus.SCHEDULED}, MailingStatus.SENTIMENT_READY, **FRESH
    )
    if won:
        logger.info(log.MAILING_SENTIMENT_READY, mailing_id=mailing_id, comments_used=comments_used)
    return won


def cancel(session: Session, mailing_id: int, expected: Collection[str], reason: str) -> bool:
    """End a mailing whose video is gone. Nothing is sent after this."""
    won = _transition(session, mailing_id, expected, MailingStatus.CANCELLED, **FRESH)
    if won:
        logger.info(log.MAILING_CANCELLED, mailing_id=mailing_id, reason=reason)
    return won


def fail(session: Session, mailing_id: int, expected: str) -> bool:
    """Give a mailing up. The caller tells the creator — after the commit."""
    won = _transition(session, mailing_id, {expected}, MailingStatus.FAILED)
    if won:
        logger.error(log.MAILING_FAILED, mailing_id=mailing_id, previous=expected)
    return won


def recipient_count(session: Session, creator_id: int) -> int:
    """How many fans would receive a mail if it went out now."""
    return session.scalar(_recipients(creator_id).with_only_columns(func.count()))


def _recipients(creator_id: int):
    """Who receives a creator's mail: confirmed, and not blocked.

    A block is permanent (ARCHITECTURE.md → "The fan area"): the provider drops
    the mail anyway, and trying costs reputation.
    """
    return (
        select(Subscription.id)
        .join(Subscriber, Subscriber.id == Subscription.subscriber_id)
        .where(
            Subscription.creator_id == creator_id,
            Subscription.status == SubscriptionStatus.CONFIRMED,
            Subscriber.blocked_at.is_(None),
        )
    )


def compose(
    session: Session,
    appearance: Appearance,
    creator: Creator,
    settings: Settings,
    **overrides,
):
    """Return a function that renders this mailing's mail for one subscription.

    The analyses are loaded once and every mail — the preview and each fan's —
    comes from the same data, so they cannot differ in anything but the parts
    that are meant to: the recipient, the action bar, the footer.
    """
    summary = load_analysis(session, appearance.id, AnalysisKind.SUMMARY)
    sentiment = load_analysis(session, appearance.id, AnalysisKind.SENTIMENT)
    view_url = f"{settings.base_url}/s/{appearance.view_token}"

    def render(subscription: Subscription | None, **extra) -> OutgoingEmail:
        return render_summary_mail(
            creator=creator,
            appearance=appearance,
            summary=summary,
            sentiment=sentiment,
            subscription=subscription,
            settings=settings,
            view_url=view_url,
            **overrides,
            **extra,
        )

    return render


def send_preview(
    session: Session,
    mailing: Mailing,
    appearance: Appearance,
    creator: Creator,
    now: datetime,
    settings: Settings,
) -> bool:
    """Send the creator the exact fan mail, then ``sentiment_ready → preview_sent``.

    ``send_at`` is pushed to at least one stop window from now *before* the
    preview is written, so a late pipeline never shortens the creator's hour.
    The payload is frozen in the same statement that records the preview: from
    here on every fan mail renders from ``render_snapshot``.

    The idempotency key carries the stop token: a retry of this preview is
    recognised by the provider, a new schedule (new token) is a new preview.
    """
    schedule = settings.schedule
    send_at = max(mailing.send_at, now + timedelta(minutes=schedule.stop_window_minutes))
    snapshot = snapshot_of(creator, effective_settings(creator, settings).email_variant)
    render = compose(session, appearance, creator, settings, snapshot=snapshot)
    preview = render(
        None,
        stop_token=mailing.stop_token,
        send_at=send_at,
        recipient_count=recipient_count(session, creator.id),
        postpone_until=postponed_send_at(send_at, appearance.published_at, schedule),
        idempotency_key=f"preview/{mailing.id}/{mailing.stop_token}",
    )
    get_services().email.send(preview)

    won = _transition(
        session,
        mailing.id,
        {MailingStatus.SENTIMENT_READY},
        MailingStatus.PREVIEW_SENT,
        send_at=send_at,
        preview_sent_at=now,
        render_snapshot=snapshot,
        **FRESH,
    )
    if won:
        logger.info(log.MAILING_PREVIEW_SENT, mailing_id=mailing.id, send_at=send_at)
    return won


def start_sending(session: Session, mailing_id: int, creator_id: int) -> bool:
    """``preview_sent → sending``, and take the recipient snapshot in the same transaction.

    Later confirmations go to the next mailing; a fan who leaves during the
    send still gets this one (owner decision 2026-09-18, plan §20 question 9).
    """
    if not _transition(
        session, mailing_id, {MailingStatus.PREVIEW_SENT}, MailingStatus.SENDING, **FRESH
    ):
        return False
    recipients = _recipients(creator_id).with_only_columns(literal(mailing_id), Subscription.id)
    session.execute(
        insert(Delivery)
        .from_select(["mailing_id", "subscription_id"], recipients)
        .on_conflict_do_nothing(index_elements=["mailing_id", "subscription_id"])
    )
    return True


def send_batches(
    session: Session,
    mailing: Mailing,
    appearance: Appearance,
    creator: Creator,
    now: datetime,
    settings: Settings,
) -> None:
    """Send every pending delivery, one batch at a time, then ``sending → sent``.

    Each batch commits on its own once the provider has accepted it. A crash
    between the call and the commit resends the same batch under the same key
    with the same payload, and the provider recognises the repeat.
    """
    render = compose(session, appearance, creator, settings)
    while batch := _pending(session, mailing.id):
        first_id = batch[0][0]
        key = f"mailing/{mailing.id}/{first_id}"
        get_services().email.send_batch(
            [
                render(subscription, snapshot=mailing.render_snapshot, idempotency_key=key)
                for _, subscription in batch
            ]
        )
        session.execute(
            update(Delivery)
            .where(Delivery.id.in_([delivery_id for delivery_id, _ in batch]))
            .values(sent_at=now)
        )
        session.commit()
        logger.info(
            log.MAILING_BATCH_SENT,
            mailing_id=mailing.id,
            size=len(batch),
            first_delivery_id=first_id,
        )

    total = session.scalar(select(func.count()).where(Delivery.mailing_id == mailing.id))
    if _transition(
        session,
        mailing.id,
        {MailingStatus.SENDING},
        MailingStatus.SENT,
        sent_at=now,
        recipient_count=total,
        **FRESH,
    ):
        logger.info(log.MAILING_SENT, mailing_id=mailing.id, recipients=total)


def _pending(session: Session, mailing_id: int) -> list[tuple[int, Subscription]]:
    """Return the next batch: pending deliveries, oldest first — the same set every time."""
    return list(
        session.execute(
            select(Delivery.id, Subscription)
            .join(Subscription, Subscription.id == Delivery.subscription_id)
            .where(Delivery.mailing_id == mailing_id, Delivery.sent_at.is_(None))
            .order_by(Delivery.id)
            .limit(BATCH_SIZE)
        ).tuples()
    )


@contextmanager
def exclusive(mailing_id: int) -> Iterator[bool]:
    """Hold the send lock for one mailing; yield whether it was obtained.

    A **session** lock on a connection of its own: a transaction lock would be
    released by the first batch's commit and leave the rest of the loop
    unprotected. If the worker dies, Postgres drops the lock with the
    connection. If the unlock fails, the connection is thrown away rather than
    returned to the pool still holding the lock.
    """
    connection = get_engine().connect()
    held = False
    try:
        held = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:id)"), {"id": mailing_id}
            ).scalar()
        )
        connection.commit()
        yield held
    finally:
        try:
            if held:
                connection.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": mailing_id})
                connection.commit()
        except Exception:
            connection.invalidate()
            raise
        finally:
            connection.close()


def find_by_token(session: Session, token: str) -> tuple[Mailing, Appearance, Creator] | None:
    """Return the mailing behind a stop token, with what a page about it needs to say."""
    return session.execute(
        select(Mailing, Appearance, Creator)
        .join(Appearance, Appearance.id == Mailing.appearance_id)
        .join(Source, Source.id == Appearance.source_id)
        .join(Creator, Creator.id == Source.creator_id)
        .where(Mailing.stop_token == token)
        # Fresh values even if this request loaded the row before: a page that
        # reports a lost race must report the state that won it.
        .execution_options(populate_existing=True)
    ).first()


def stop(session: Session, token: str, now: datetime) -> bool:
    """Stop the send — the creator's emergency brake, one conditional statement."""
    mailing_id = session.scalar(
        update(Mailing)
        .where(Mailing.stop_token == token, Mailing.status.in_(list(MAILING_STOPPABLE)))
        .values(status=MailingStatus.STOPPED, stopped_at=now)
        .returning(Mailing.id)
    )
    if mailing_id is None:
        return False
    logger.info(log.MAILING_STOPPED, mailing_id=mailing_id)
    return True


def postpone(session: Session, token: str, seen_send_at: datetime, new_send_at: datetime) -> bool:
    """Move the send and start the schedule over: new token, new sentiment, new preview.

    ``seen_send_at`` guards against the preview step pushing ``send_at`` between
    the page's read and this write: the new time was computed from the old one.
    """
    mailing_id = session.scalar(
        update(Mailing)
        .where(
            Mailing.stop_token == token,
            Mailing.status.in_(list(MAILING_STOPPABLE)),
            Mailing.send_at == seen_send_at,
        )
        .values(
            status=MailingStatus.SCHEDULED,
            send_at=new_send_at,
            stop_token=new_token(),
            preview_sent_at=None,
            render_snapshot=None,
            **FRESH,
        )
        .returning(Mailing.id)
    )
    if mailing_id is None:
        return False
    logger.info(log.MAILING_POSTPONED, mailing_id=mailing_id, old=seen_send_at, new=new_send_at)
    return True
