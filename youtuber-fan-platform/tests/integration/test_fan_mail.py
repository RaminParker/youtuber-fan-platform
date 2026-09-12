"""The mail a fan actually receives — the path no preview exercises."""

from datetime import UTC, datetime

import pytest

from app.analysis.schemas import Sentiment, Summary
from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import (
    Appearance,
    AppearanceStatus,
    Creator,
    Source,
    SourceKind,
    Subscriber,
    Subscription,
    SubscriptionStatus,
)
from app.delivery.render import render_summary_mail
from tests.fakes import _default_for

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def subscription(committed_database):
    """A confirmed fan of a pilot creator, with a video ready to be mailed."""
    with session_scope() as session:
        creator = Creator(slug="pilot", name="Pilotkanal", contact_email="pilot@example.org")
        session.add(creator)
        session.flush()
        source = Source(creator_id=creator.id, kind=SourceKind.YOUTUBE, external_id="UCp")
        session.add(source)
        session.flush()
        appearance = Appearance(
            source_id=source.id,
            external_id="aaaaaaaaaaa",
            title="Ein Video",
            url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
            published_at=NOW,
            duration_seconds=900,
            status=AppearanceStatus.ANALYZED,
            view_token="tok",
        )
        session.add(appearance)
        subscriber = Subscriber(email="fan@example.org")
        session.add(subscriber)
        session.flush()
        subscription = Subscription(
            subscriber_id=subscriber.id,
            creator_id=creator.id,
            status=SubscriptionStatus.CONFIRMED,
            confirmed_at=NOW,
            unsubscribe_token="unsub-token",
        )
        session.add(subscription)
        session.commit()
        return subscription.id


class TestAddressingAFan:
    """The composer has to find the recipient's address from the subscription."""

    def test_the_mail_goes_to_the_subscriber(self, subscription):
        with session_scope() as session:
            row = session.get(Subscription, subscription)
            creator = session.get(Creator, row.creator_id)
            appearance = session.scalar(__import__("sqlalchemy").select(Appearance))

            mail = render_summary_mail(
                creator=creator,
                appearance=appearance,
                summary=_default_for(Summary),
                sentiment=_default_for(Sentiment),
                subscription=row,
                settings=get_settings(),
                variant="compact",
                view_url="http://testserver/s/tok",
            )

        assert mail.to == "fan@example.org"

    def test_and_carries_that_subscriptions_unsubscribe_link(self, subscription):
        with session_scope() as session:
            row = session.get(Subscription, subscription)
            creator = session.get(Creator, row.creator_id)
            appearance = session.scalar(__import__("sqlalchemy").select(Appearance))

            mail = render_summary_mail(
                creator=creator,
                appearance=appearance,
                summary=_default_for(Summary),
                sentiment=None,
                subscription=row,
                settings=get_settings(),
                variant="compact",
                view_url="http://testserver/s/tok",
            )

        assert "unsub-token" in mail.headers["List-Unsubscribe"]
        assert "unsub-token" in mail.text
