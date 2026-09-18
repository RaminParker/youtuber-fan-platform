"""The daily cleanup: sign-ups that were never confirmed, and fans who left."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import (
    BlockedReason,
    Creator,
    Subscriber,
    Subscription,
    SubscriptionStatus,
)
from app.jobs import steps
from app.tokens import new_token

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 18, 12, tzinfo=UTC)


def add(session, creator, address, status, *, blocked=None, **values) -> Subscription:
    subscriber = session.scalar(select(Subscriber).where(Subscriber.email == address))
    if subscriber is None:
        subscriber = Subscriber(email=address, blocked_reason=blocked)
        subscriber.blocked_at = NOW if blocked else None
        session.add(subscriber)
        session.flush()
    subscription = Subscription(
        subscriber_id=subscriber.id,
        creator_id=creator.id,
        status=status,
        unsubscribe_token=new_token(),
        **values,
    )
    session.add(subscription)
    session.flush()
    return subscription


@pytest.fixture
def creator(session):
    creator = Creator(slug="pilot", name="Pilot", contact_email="pilot@example.org")
    session.add(creator)
    session.flush()
    return creator


def addresses(session) -> set[str]:
    return set(session.scalars(select(Subscriber.email)))


def statuses(session) -> dict[str, str]:
    rows = session.execute(
        select(Subscriber.email, Subscription.status).join(
            Subscription, Subscription.subscriber_id == Subscriber.id
        )
    )
    return dict(rows.all())


class TestCleanup:
    def test_expired_sign_ups_go_fresh_ones_stay(self, session, creator):
        pending = SubscriptionStatus.PENDING
        add(session, creator, "old@x.org", pending, confirm_expires_at=NOW - timedelta(seconds=1))
        add(session, creator, "new@x.org", pending, confirm_expires_at=NOW + timedelta(days=1))

        steps.cleanup(session, NOW, get_settings())

        assert statuses(session) == {"new@x.org": pending}
        assert addresses(session) == {"new@x.org"}

    def test_unsubscribed_rows_go_after_the_retention(self, session, creator):
        days = get_settings().email.unsubscribed_retention_days
        gone = SubscriptionStatus.UNSUBSCRIBED
        add(session, creator, "old@x.org", gone, unsubscribed_at=NOW - timedelta(days=days + 1))
        add(session, creator, "new@x.org", gone, unsubscribed_at=NOW - timedelta(days=days - 1))

        steps.cleanup(session, NOW, get_settings())

        assert statuses(session) == {"new@x.org": gone}

    def test_confirmed_fans_stay_whatever_their_age(self, session, creator):
        add(
            session,
            creator,
            "fan@x.org",
            SubscriptionStatus.CONFIRMED,
            confirm_expires_at=NOW - timedelta(days=400),
        )

        steps.cleanup(session, NOW, get_settings())

        assert addresses(session) == {"fan@x.org"}

    def test_a_complaint_is_never_forgotten(self, session, creator):
        # A person who reported spam must stay blocked even after their last
        # subscription is gone: a new sign-up would otherwise write to them.
        add(
            session,
            creator,
            "spam@x.org",
            SubscriptionStatus.PENDING,
            blocked=BlockedReason.COMPLAINT,
            confirm_expires_at=NOW - timedelta(days=1),
        )

        steps.cleanup(session, NOW, get_settings())

        assert addresses(session) == {"spam@x.org"}
        assert session.scalar(select(func.count()).select_from(Subscription)) == 0

    def test_a_bounced_address_without_subscriptions_is_deleted(self, session, creator):
        # A mistyped address that bounced has nothing to protect: the mail
        # provider keeps its own suppression entry, and we keep no data we do
        # not need (manifest §7.9).
        add(
            session,
            creator,
            "typo@gmial.com",
            SubscriptionStatus.PENDING,
            blocked=BlockedReason.BOUNCE,
            confirm_expires_at=NOW - timedelta(days=1),
        )

        steps.cleanup(session, NOW, get_settings())

        assert addresses(session) == set()

    def test_an_address_still_following_another_creator_stays(self, session, creator):
        other = Creator(slug="other", name="Other", contact_email="other@example.org")
        session.add(other)
        session.flush()
        expired = NOW - timedelta(seconds=1)
        add(session, creator, "fan@x.org", SubscriptionStatus.PENDING, confirm_expires_at=expired)
        add(session, other, "fan@x.org", SubscriptionStatus.CONFIRMED)

        steps.cleanup(session, NOW, get_settings())

        assert addresses(session) == {"fan@x.org"}


class TestCleanupAgainstASignUp:
    """The daily sweep must never delete what a sign-up is working on."""

    def test_an_address_a_sign_up_holds_is_skipped(self, committed_database):
        with session_scope() as setup:
            setup.add(Subscriber(email="fan@x.org"))

        with session_scope() as sign_up:
            # The sign-up has locked the address and is about to add a subscription.
            sign_up.scalars(select(Subscriber).with_for_update()).one()

            with session_scope() as sweep:
                sweep.execute(text("SET LOCAL lock_timeout = '2s'"))
                steps.cleanup(sweep, NOW, get_settings())

        with session_scope() as check:
            assert check.scalar(select(Subscriber.email)) == "fan@x.org"
