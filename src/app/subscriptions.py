"""A fan's subscriptions: signing up, confirming, and the confirm mail.

The routes in ``web/routes/fan.py`` translate HTTP into calls to this module;
the rules live here, where they can be tested without a request.

Three rules hold it together (plan §10, with the deviations recorded there):

- **The public form can only add, never take away.** A confirmed fan who signs
  up again gets the confirm mail again and nothing else changes.
- **A blocked address gets nothing, ever.** Bounce and complaint blocks mirror
  the mail provider's own suppression list, which does not expire; lifting one
  is an operator's decision (ARCHITECTURE.md → "The fan area").
- **At most one confirm mail per address per window**, across all creators,
  because the per-IP limit alone can be forged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import log
from app.config import Settings, get_settings
from app.db.engine import session_scope
from app.db.models import (
    Appearance,
    AppearanceStatus,
    Creator,
    Mailing,
    MailingStatus,
    Source,
    Subscriber,
    Subscription,
    SubscriptionStatus,
)
from app.delivery.render import render_confirm_mail
from app.services import get_services
from app.tokens import new_token

logger = log.get_logger(__name__)


@dataclass(frozen=True)
class ConfirmMail:
    """A confirm mail that is due: everything needed to send it, and to undo."""

    subscription_id: int
    address: str
    token: str
    sent_at: datetime


def record_sign_up(
    session: Session, creator: Creator, address: str, now: datetime, settings: Settings
) -> ConfirmMail | None:
    """Apply the sign-up rules; return the confirm mail that is now due.

    ``None`` means: send nothing, answer as usual — the address is blocked, or
    it was sent a confirm mail within ``web.confirm_resend_minutes``.

    Parameters
    ----------
    address
        Already validated and in its stored spelling (``app.addresses``).
    """
    subscriber = _locked_upsert(session, Subscriber, {"email": address}, "email")
    if subscriber.blocked_at is not None:
        return None
    if _recently_mailed(session, subscriber, now, settings):
        return None

    subscription = _locked_upsert(
        session,
        Subscription,
        {
            "subscriber_id": subscriber.id,
            "creator_id": creator.id,
            "status": SubscriptionStatus.PENDING,
            "unsubscribe_token": new_token(),
        },
        "subscriber_id",
        "creator_id",
    )
    if subscription.status != SubscriptionStatus.CONFIRMED:
        subscription.status = SubscriptionStatus.PENDING
        subscription.confirm_token = new_token()
        subscription.confirm_expires_at = now + timedelta(days=settings.email.confirm_token_days)
        subscription.unsubscribed_at = None
        logger.info(log.SUBSCRIPTION_CREATED, subscription_id=subscription.id)
    subscription.confirm_sent_at = now
    return ConfirmMail(subscription.id, address, subscription.confirm_token, now)


def _locked_upsert[Row](session: Session, model: type[Row], values: dict, *unique: str) -> Row:
    """Insert a row unless it exists; either way return it, locked.

    ``DO UPDATE`` rather than ``DO NOTHING``: it always returns the row and
    locks it in the same statement (the no-op update writes a unique column to
    itself). Two sign-ups of one address therefore run one after the other —
    the second sees the first one's confirm mail and is throttled — and the
    daily cleanup cannot delete the row in between.
    """
    statement = insert(model).values(**values)
    statement = statement.on_conflict_do_update(
        index_elements=list(unique), set_={unique[-1]: statement.excluded[unique[-1]]}
    )
    return session.scalars(
        statement.returning(model), execution_options={"populate_existing": True}
    ).one()


def _recently_mailed(
    session: Session, subscriber: Subscriber, now: datetime, settings: Settings
) -> bool:
    """Tell whether this address got a confirm mail, for any creator, within the window.

    Per address, not per subscription: otherwise every creator on the platform
    would be one more mail per window into a stranger's inbox.
    """
    last_sent = session.scalar(
        select(func.max(Subscription.confirm_sent_at)).where(
            Subscription.subscriber_id == subscriber.id
        )
    )
    window = timedelta(minutes=settings.web.confirm_resend_minutes)
    return last_sent is not None and last_sent + window > now


def send_confirm_mail(creator: Creator, due: ConfirmMail) -> None:
    """Send a confirm mail once the sign-up is committed and answered.

    Runs after the response has gone out, so the answer takes as long for a
    blocked or throttled address — which sends nothing — as for a new one: the
    response time must not reveal who is subscribed or who complained. Needs
    no database read: the request already had everything. On failure the
    throttle is released, because no mail left.

    ``# ponytail: the same send-then-undo shape as the magic link in
    web/routes/creator.py; extract a helper when a third mail needs it.``
    """
    settings = get_settings()
    link = f"{settings.base_url}/k/{creator.slug}/bestaetigen/{due.token}"
    try:
        get_services().email.send(render_confirm_mail(creator, due.address, link, settings))
    except Exception:
        logger.exception(log.SUBSCRIPTION_CONFIRM_FAILED, subscription_id=due.subscription_id)
        _release_throttle(due)
        return
    logger.info(log.SUBSCRIPTION_CONFIRM_SENT, subscription_id=due.subscription_id)


def _release_throttle(due: ConfirmMail) -> None:
    """Undo ``confirm_sent_at`` — unless a later sign-up has set it anew."""
    with session_scope() as session:
        session.execute(
            update(Subscription)
            .where(
                Subscription.id == due.subscription_id,
                Subscription.confirm_sent_at == due.sent_at,
            )
            .values(confirm_sent_at=None)
        )


def confirmable(subscription: Subscription, now: datetime) -> bool:
    """Tell whether the link still confirms: confirmed already, or pending and in time.

    An unsubscribed fan's old link does not count: a fetched link must not
    undo a decision to leave.
    """
    if subscription.status == SubscriptionStatus.CONFIRMED:
        return True
    return (
        subscription.status == SubscriptionStatus.PENDING
        and subscription.confirm_expires_at is not None
        and subscription.confirm_expires_at > now
    )


def confirm(subscription: Subscription, now: datetime) -> None:
    """Confirm a pending sign-up; an already confirmed one stays as it is."""
    if subscription.status != SubscriptionStatus.PENDING:
        return
    subscription.status = SubscriptionStatus.CONFIRMED
    subscription.confirmed_at = now
    logger.info(log.SUBSCRIPTION_CONFIRMED, subscription_id=subscription.id)


def newest_received_summary(session: Session, creator: Creator) -> str | None:
    """Return the view token of the newest summary the list has already received.

    Back catalogue, or a mailing that went out. Never an open, stopped or
    cancelled one: the page must not hand out a summary before the list gets
    it, or after the creator decided it should not go out (manifest §3.1).
    """
    return session.scalar(
        select(Appearance.view_token)
        .join(Source, Source.id == Appearance.source_id)
        .outerjoin(Mailing, Mailing.appearance_id == Appearance.id)
        .where(
            Source.creator_id == creator.id,
            Appearance.status == AppearanceStatus.ANALYZED,
            or_(Appearance.is_backfill, Mailing.status == MailingStatus.SENT),
        )
        .order_by(Appearance.published_at.desc())
        .limit(1)
    )


def unsubscribe(session: Session, token: str, now: datetime) -> Creator | None:
    """Unsubscribe the one subscription behind this token; return its creator.

    The first date is kept: a second click changes nothing.
    """
    subscription_id = session.scalar(
        update(Subscription)
        .where(
            Subscription.unsubscribe_token == token,
            Subscription.status != SubscriptionStatus.UNSUBSCRIBED,
        )
        .values(status=SubscriptionStatus.UNSUBSCRIBED, unsubscribed_at=now)
        .returning(Subscription.id)
    )
    if subscription_id is not None:
        logger.info(log.SUBSCRIPTION_UNSUBSCRIBED, subscription_id=subscription_id)
    return creator_for_unsubscribe(session, token)


def creator_for_unsubscribe(session: Session, token: str) -> Creator | None:
    """Return the creator a fan is leaving, to name on the page."""
    return session.scalar(
        select(Creator)
        .join(Subscription, Subscription.creator_id == Creator.id)
        .where(Subscription.unsubscribe_token == token)
    )
