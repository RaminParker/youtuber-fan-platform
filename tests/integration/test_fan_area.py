"""The fan area: double opt-in, unsubscribing, and the bounce webhook."""

import base64
import hashlib
import hmac
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import (
    Appearance,
    AppearanceStatus,
    BlockedReason,
    Creator,
    Mailing,
    MailingStatus,
    Source,
    SourceKind,
    Subscriber,
    Subscription,
    SubscriptionStatus,
)
from app.delivery.email_client import EmailTemporaryError
from app.services import set_services
from app.web.server import create_app
from tests import fakes
from tests.fakes import FakeEmailClient

pytestmark = pytest.mark.integration

FAN = "fan@example.org"
SECRET = "whsec_" + base64.b64encode(b"a-shared-secret-for-webhooks").decode()
ANSWER = "Schau in dein Postfach"


@pytest.fixture
def mailer():
    return FakeEmailClient()


@pytest.fixture
def client(committed_database, monkeypatch, mailer, fake_services):
    monkeypatch.setenv("BASE_URL", "http://testserver")
    monkeypatch.setenv("RESEND_WEBHOOK_SECRET", SECRET)
    get_settings.cache_clear()
    set_services(fakes.services(email=mailer))
    with session_scope() as session:
        for slug in ("pilot", "other"):
            creator = Creator(slug=slug, name=f"Kanal {slug}", contact_email=f"{slug}@example.org")
            session.add(creator)
            session.flush()
            session.add(Source(creator_id=creator.id, kind=SourceKind.YOUTUBE, external_id=slug))
    with TestClient(create_app(), follow_redirects=False) as client:
        yield client


def sign_up(client, address=FAN, slug="pilot", **headers):
    return client.post(f"/k/{slug}", data={"email": address}, headers=headers)


def confirm_path(mailer) -> str:
    return "/k/" + mailer.last.text.split("/k/", 1)[1].split()[0]


def subscription(slug="pilot", address=FAN) -> Subscription | None:
    with session_scope() as session:
        found = session.scalar(
            select(Subscription)
            .join(Creator, Creator.id == Subscription.creator_id)
            .join(Subscriber, Subscriber.id == Subscription.subscriber_id)
            .where(Creator.slug == slug, Subscriber.email == address)
        )
        session.expunge_all()
        return found


def update_subscription(**values) -> None:
    with session_scope() as session:
        row = session.get(Subscription, subscription().id)
        for key, value in values.items():
            setattr(row, key, value)


def block(address: str, reason: BlockedReason) -> None:
    with session_scope() as session:
        session.add(Subscriber(email=address, blocked_at=datetime.now(UTC), blocked_reason=reason))


def subscriber(address=FAN) -> Subscriber | None:
    with session_scope() as session:
        found = session.scalar(select(Subscriber).where(Subscriber.email == address))
        session.expunge_all()
        return found


class TestDoubleOptIn:
    def test_sign_up_then_confirm(self, client, mailer):
        response = sign_up(client)

        assert response.status_code == 200
        assert ANSWER in response.text
        assert mailer.last.to == FAN
        assert subscription().status == SubscriptionStatus.PENDING

        page = client.get(confirm_path(mailer))

        assert page.status_code == 200
        assert "Dabei" in page.text
        assert subscription().status == SubscriptionStatus.CONFIRMED
        assert subscription().confirmed_at is not None

    def test_the_address_is_normalised(self, client, mailer):
        sign_up(client, address="  Fan@Example.ORG ")

        assert mailer.last.to == FAN
        assert subscription() is not None

    def test_the_confirm_mail_is_the_creators_and_has_no_summary_link(self, client, mailer):
        sign_up(client)

        mail = mailer.last
        assert mail.from_.startswith("Kanal pilot via ")
        assert "/s/" not in mail.text and "/s/" not in mail.html
        assert "/bestaetigen/" in mail.html

    def test_confirming_twice_shows_the_same_page(self, client, mailer):
        # A link scanner may fetch the link before the person clicks it.
        sign_up(client)
        first = client.get(confirm_path(mailer))
        second = client.get(confirm_path(mailer))

        assert first.status_code == second.status_code == 200
        assert "Dabei" in second.text

    def test_an_expired_link_offers_a_new_sign_up(self, client, mailer):
        sign_up(client)
        update_subscription(confirm_expires_at=datetime.now(UTC) - timedelta(seconds=1))

        page = client.get(confirm_path(mailer))

        assert page.status_code == 410
        assert 'action="/k/pilot"' in page.text
        assert subscription().status == SubscriptionStatus.PENDING

    def test_an_unknown_link_offers_a_new_sign_up(self, client):
        page = client.get("/k/pilot/bestaetigen/nonsense")

        assert page.status_code == 410
        assert 'action="/k/pilot"' in page.text

    def test_htmx_gets_only_the_fragment(self, client):
        response = sign_up(client, **{"HX-Request": "true"})

        assert ANSWER in response.text
        assert "<html" not in response.text

    def test_the_page_loads_htmx(self, client):
        assert "/static/htmx.min.js" in client.get("/k/pilot").text
        assert client.get("/static/htmx.min.js").status_code == 200

    def test_an_invalid_address_sends_nothing(self, client, mailer):
        response = sign_up(client, address="not-an-address")

        assert "gültige E-Mail-Adresse" in response.text
        assert mailer.sent == []

    def test_an_unknown_creator_is_a_404(self, client, mailer):
        assert sign_up(client, slug="nobody").status_code == 404
        assert mailer.sent == []


class TestNoEnumeration:
    def test_new_and_confirmed_addresses_get_the_same_answer(self, client, mailer):
        new = sign_up(client, address="new@example.org").text
        sign_up(client)
        client.get(confirm_path(mailer))
        update_subscription(confirm_sent_at=None)

        known = sign_up(client).text

        assert new == known

    def test_a_complained_address_gets_the_same_answer_and_no_mail(self, client, mailer):
        block(FAN, BlockedReason.COMPLAINT)

        response = sign_up(client)

        assert ANSWER in response.text
        assert mailer.sent == []

    def test_a_broken_mail_provider_gives_the_same_answer(self, client, mailer):
        mailer.fail_with = EmailTemporaryError("down")

        response = sign_up(client)

        assert response.status_code == 200
        assert ANSWER in response.text

    def test_and_does_not_throttle_the_retry(self, client, mailer):
        mailer.fail_with = EmailTemporaryError("down")
        sign_up(client)
        mailer.fail_with = None

        sign_up(client)

        assert mailer.to(FAN)


class TestStateRules:
    def test_a_confirmed_fan_is_never_demoted(self, client, mailer):
        sign_up(client)
        client.get(confirm_path(mailer))
        before = subscription()
        update_subscription(confirm_sent_at=None)

        sign_up(client)

        after = subscription()
        assert len(mailer.sent) == 2
        assert after.status == SubscriptionStatus.CONFIRMED
        assert after.confirm_token == before.confirm_token
        assert after.confirmed_at == before.confirmed_at
        assert "Dabei" in client.get(confirm_path(mailer)).text

    def test_a_pending_sign_up_gets_a_fresh_token(self, client, mailer):
        sign_up(client)
        old = subscription().confirm_token
        update_subscription(confirm_sent_at=None)

        sign_up(client)

        assert subscription().confirm_token != old
        assert client.get(f"/k/pilot/bestaetigen/{old}").status_code == 410

    def test_an_unsubscribed_fan_can_sign_up_again(self, client, mailer):
        sign_up(client)
        client.get(confirm_path(mailer))
        client.post(f"/abmelden/{subscription().unsubscribe_token}")
        update_subscription(confirm_sent_at=None)

        sign_up(client)

        assert subscription().status == SubscriptionStatus.PENDING
        client.get(confirm_path(mailer))
        assert subscription().status == SubscriptionStatus.CONFIRMED

    def test_an_old_confirm_link_does_not_undo_an_unsubscribe(self, client, mailer):
        # GET must not change state behind a person's back; this one would.
        sign_up(client)
        link = confirm_path(mailer)
        client.get(link)
        client.post(f"/abmelden/{subscription().unsubscribe_token}")

        client.get(link)

        assert subscription().status == SubscriptionStatus.UNSUBSCRIBED

    def test_a_bounced_address_gets_the_mail_and_confirming_lifts_the_block(self, client, mailer):
        block(FAN, BlockedReason.BOUNCE)

        sign_up(client)
        client.get(confirm_path(mailer))

        assert subscriber().blocked_at is None
        assert subscriber().blocked_reason is None

    def test_a_complaint_block_is_never_lifted(self, client, mailer):
        sign_up(client)
        link = confirm_path(mailer)
        with session_scope() as session:
            row = session.scalar(select(Subscriber))
            row.blocked_at, row.blocked_reason = datetime.now(UTC), BlockedReason.COMPLAINT

        client.get(link)

        assert subscriber().blocked_reason == BlockedReason.COMPLAINT


class TestBrakes:
    def test_the_ip_limit_answers_429(self, client):
        limit = int(get_settings().web.rate_limit_signup.split("/")[0])

        codes = [sign_up(client, address=f"f{i}@example.org").status_code for i in range(limit + 1)]

        assert codes[:limit] == [200] * limit
        assert codes[limit] == 429

    def test_one_confirm_mail_per_address_and_window(self, client, mailer):
        for _ in range(3):
            response = sign_up(client)

        assert ANSWER in response.text
        assert len(mailer.sent) == 1

    def test_the_window_passes(self, client, mailer):
        sign_up(client)
        minutes = get_settings().web.confirm_resend_minutes
        update_subscription(confirm_sent_at=datetime.now(UTC) - timedelta(minutes=minutes))

        sign_up(client)

        assert len(mailer.sent) == 2

    def test_the_window_is_per_creator(self, client, mailer):
        sign_up(client)
        sign_up(client, slug="other")

        assert len(mailer.sent) == 2


class TestConfirmationPageLink:
    """The page may only hand out what the list has already received."""

    @staticmethod
    def add_video(video_id, *, days_ago, backfill=False, mailing=None):
        with session_scope() as session:
            source = session.scalar(select(Source).where(Source.external_id == "pilot"))
            appearance = Appearance(
                source_id=source.id,
                external_id=video_id,
                title=video_id,
                url=f"https://www.youtube.com/watch?v={video_id}",
                published_at=datetime.now(UTC) - timedelta(days=days_ago),
                status=AppearanceStatus.ANALYZED,
                is_backfill=backfill,
                view_token=f"token-{video_id}",
            )
            session.add(appearance)
            session.flush()
            if mailing:
                session.add(
                    Mailing(
                        appearance_id=appearance.id,
                        status=mailing,
                        send_at=datetime.now(UTC),
                        stop_token=f"stop-{video_id}",
                    )
                )

    def confirmed_page(self, client, mailer) -> str:
        sign_up(client)
        return client.get(confirm_path(mailer)).text

    def test_links_the_newest_sent_video(self, client, mailer):
        self.add_video("backfilled0", days_ago=30, backfill=True)
        self.add_video("sentvideo00", days_ago=10, mailing=MailingStatus.SENT)

        assert "/s/token-sentvideo00" in self.confirmed_page(client, mailer)

    @pytest.mark.parametrize(
        "status", [MailingStatus.SCHEDULED, MailingStatus.STOPPED, MailingStatus.CANCELLED]
    )
    def test_never_one_the_list_has_not_received(self, client, mailer, status):
        self.add_video("backfilled0", days_ago=30, backfill=True)
        self.add_video("notsentyet0", days_ago=1, mailing=status)

        page = self.confirmed_page(client, mailer)

        assert "/s/token-notsentyet0" not in page
        assert "/s/token-backfilled0" in page

    def test_no_link_without_a_summary(self, client, mailer):
        assert "/s/" not in self.confirmed_page(client, mailer)


class TestUnsubscribe:
    def test_the_link_only_shows_a_button(self, client, mailer):
        sign_up(client)
        client.get(confirm_path(mailer))

        page = client.get(f"/abmelden/{subscription().unsubscribe_token}")

        assert page.status_code == 200
        assert "<form" in page.text
        assert subscription().status == SubscriptionStatus.CONFIRMED

    def test_both_pages_name_the_creator(self, client, mailer):
        # A fan following several channels must see which one they are leaving.
        sign_up(client)
        path = f"/abmelden/{subscription().unsubscribe_token}"

        assert "Kanal pilot" in client.get(path).text
        assert "Kanal pilot" in client.post(path).text

    def test_it_affects_only_that_subscription(self, client, mailer):
        for slug in ("pilot", "other"):
            sign_up(client, slug=slug)
            client.get(confirm_path(mailer))

        response = client.post(f"/abmelden/{subscription().unsubscribe_token}")

        assert response.status_code == 200
        assert subscription().status == SubscriptionStatus.UNSUBSCRIBED
        assert subscription().unsubscribed_at is not None
        assert subscription(slug="other").status == SubscriptionStatus.CONFIRMED

    def test_one_click_from_the_mail_client(self, client, mailer):
        sign_up(client)
        token = subscription().unsubscribe_token

        response = client.post(f"/abmelden/{token}", data={"List-Unsubscribe": "One-Click"})

        assert response.status_code == 200
        assert subscription().status == SubscriptionStatus.UNSUBSCRIBED

    def test_twice_keeps_the_first_date(self, client, mailer):
        sign_up(client)
        token = subscription().unsubscribe_token
        client.post(f"/abmelden/{token}")
        first = subscription().unsubscribed_at

        client.post(f"/abmelden/{token}")

        assert subscription().unsubscribed_at == first

    def test_an_unknown_token_still_answers_200(self, client):
        response = client.post("/abmelden/nonsense")

        assert response.status_code == 200
        assert "--accent: #333333" in response.text


def webhook(client, event: dict | bytes, *, secret=SECRET):
    body = event if isinstance(event, bytes) else json.dumps(event).encode()
    message_id, timestamp = "msg_1", str(int(time.time()))
    key = base64.b64decode(secret.removeprefix("whsec_"))
    digest = hmac.new(key, f"{message_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    headers = {
        "svix-id": message_id,
        "svix-timestamp": timestamp,
        "svix-signature": "v1," + base64.b64encode(digest).decode(),
        "content-type": "application/json",
    }
    return client.post("/webhooks/resend", content=body, headers=headers)


def bounced(address=FAN, bounce_type="Permanent") -> dict:
    return {
        "type": "email.bounced",
        "data": {"to": [address], "bounce": {"type": bounce_type, "subType": "Suppressed"}},
    }


def complained(address=FAN) -> dict:
    return {"type": "email.complained", "data": {"to": [address]}}


class TestWebhook:
    @pytest.fixture(autouse=True)
    def known_fan(self, client, mailer):
        sign_up(client)
        client.get(confirm_path(mailer))

    def test_a_bounce_blocks(self, client):
        assert webhook(client, bounced()).status_code == 200

        assert subscriber().blocked_reason == BlockedReason.BOUNCE
        assert subscriber().blocked_at is not None

    def test_a_replay_changes_nothing(self, client):
        webhook(client, bounced())
        first = subscriber().blocked_at

        webhook(client, bounced())

        assert subscriber().blocked_at == first

    def test_a_transient_bounce_does_not_block(self, client):
        webhook(client, bounced(bounce_type="Transient"))

        assert subscriber().blocked_at is None

    def test_a_complaint_blocks_for_good(self, client):
        webhook(client, bounced())
        webhook(client, complained())

        # A complaint outranks a bounce: a bounce block is lifted by the next
        # confirmation, and a person who reported spam must never get one.
        assert subscriber().blocked_reason == BlockedReason.COMPLAINT

    def test_a_forged_signature_is_refused_and_changes_nothing(self, client):
        # 401, not 200: with a wrong secret configured, the provider's dashboard
        # shows the failures and retries, instead of every bounce vanishing.
        other = "whsec_" + base64.b64encode(b"somebody-else").decode()

        response = webhook(client, bounced(), secret=other)

        assert response.status_code == 401
        assert subscriber().blocked_at is None

    def test_an_unsigned_request_is_refused(self, client):
        assert client.post("/webhooks/resend", content=b"nonsense").status_code == 401

    def test_other_events_and_unknown_addresses_are_ignored(self, client):
        assert (
            webhook(client, {"type": "email.delivered", "data": {"to": [FAN]}}).status_code == 200
        )
        assert webhook(client, bounced("stranger@example.org")).status_code == 200
        assert subscriber().blocked_at is None
        assert subscriber("stranger@example.org") is None

    def test_the_address_is_matched_case_insensitively(self, client):
        webhook(client, bounced("FAN@example.org"))

        assert subscriber().blocked_reason == BlockedReason.BOUNCE

    def test_a_signed_body_that_is_not_json_is_ignored(self, client):
        # Retrying would not make it readable; acknowledge and move on.
        assert webhook(client, b"nonsense").status_code == 200
