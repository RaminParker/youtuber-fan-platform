"""The mailing lifecycle, driven by the worker with a stepped clock.

Everything here commits for real (``committed_database``): the worker, the
advisory lock and the batch loop all open their own sessions, and the property
under test — exactly once — only exists across those commits.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError

from app import worker
from app.analysis.schemas import Sentiment, Summary
from app.config import get_settings
from app.db.engine import get_engine, session_scope
from app.db.models import (
    Analysis,
    AnalysisKind,
    Appearance,
    AppearanceStatus,
    Creator,
    Delivery,
    JobRun,
    LLMCall,
    Mailing,
    MailingStatus,
    NoticeKind,
    Source,
    SourceKind,
    Subscriber,
    Subscription,
    SubscriptionStatus,
    Transcript,
)
from app.delivery import mailing as mailings
from app.delivery.email_client import EmailError, EmailTemporaryError, QuotaExhausted
from app.delivery.render import NOTICES
from app.errors import NeedsOperator, TemporaryError
from app.jobs import steps
from app.jobs.schedule import MAX_ATTEMPTS
from app.services import set_services
from app.web.server import create_app
from tests import fakes
from tests.fakes import Comment, FakeEmailClient, FakeYouTubeConnector, _default_for, content_item

pytestmark = pytest.mark.integration

VIDEO = "vvvvvvvvvvv"
CREATOR_MAIL = "pilot@example.org"
T = datetime(2026, 9, 22, 16, 0, tzinfo=UTC)  # Dienstag, 18:00 in Berlin
PUBLISHED = T - timedelta(days=7)
SENTIMENT_AT = T - timedelta(hours=2)
PREVIEW_AT = T - timedelta(hours=1)

COMMENTS = [
    Comment(text="Sehr gute Analyse der Zuständigkeiten, danke dafür", like_count=12,
            author_channel_id="UCfan1"),
    Comment(text="Bei den Zahlen aus Minute zwölf bin ich anderer Meinung", like_count=3,
            author_channel_id="UCfan2"),
]  # fmt: skip


@pytest.fixture
def world(committed_database, fake_services):
    """A creator with one analysed video whose mailing is scheduled for T."""
    with session_scope() as session:
        creator = Creator(
            slug="pilot",
            name="Pilotkanal",
            contact_email=CREATOR_MAIL,
            greeting_text="Servus!",
            email_variant="compact",
        )
        session.add(creator)
        session.flush()
        source = Source(creator_id=creator.id, kind=SourceKind.YOUTUBE, external_id="UCpilot")
        other = Creator(slug="other", name="Anderer Kanal", contact_email="other@example.org")
        session.add_all([source, other])
        session.flush()
        appearance = Appearance(
            source_id=source.id,
            external_id=VIDEO,
            title="Warum Verwaltung so langsam ist",
            url=f"https://www.youtube.com/watch?v={VIDEO}",
            published_at=PUBLISHED,
            duration_seconds=1200,
            status=AppearanceStatus.ANALYZED,
            view_token="view-token",
        )
        session.add(appearance)
        session.flush()
        session.add(
            Analysis(
                appearance_id=appearance.id,
                kind=AnalysisKind.SUMMARY,
                prompt_version="v1",
                model="fake",
                content=_default_for(Summary).model_dump(mode="json"),
            )
        )
        # The periodic jobs reach the network (the public feed); here they have
        # "just run", so every tick exercises the mailing steps alone.
        session.add_all(
            JobRun(name=name, last_run_at=T + timedelta(days=365))
            for name in (steps.POLL_FEEDS, steps.CLEANUP)
        )
        mailing = Mailing(
            appearance_id=appearance.id,
            status=MailingStatus.SCHEDULED,
            send_at=T,
            stop_token="stop-token-1",
        )
        session.add(mailing)
        session.flush()
        return {"creator": creator.id, "other": other.id, "mailing": mailing.id}


def install(**kwargs) -> tuple[FakeEmailClient, FakeYouTubeConnector]:
    """Swap in fakes: by default a public video with two good comments."""
    email = kwargs.pop("email", None) or FakeEmailClient()
    youtube = kwargs.pop("youtube", None) or FakeYouTubeConnector(
        items=[content_item(VIDEO)], comments=COMMENTS
    )
    set_services(fakes.services(email=email, youtube=youtube, **kwargs))
    return email, youtube


def add_fan(creator_id: int, address: str, status=SubscriptionStatus.CONFIRMED, **subscriber):
    with session_scope() as session:
        fan = Subscriber(email=address, **subscriber)
        session.add(fan)
        session.flush()
        row = Subscription(
            subscriber_id=fan.id,
            creator_id=creator_id,
            status=status,
            confirmed_at=PUBLISHED if status == SubscriptionStatus.CONFIRMED else None,
            unsubscribe_token=f"unsub-{address}",
        )
        session.add(row)
        session.flush()
        return row.id


def logged(caplog, event: str) -> bool:
    return any(event in str(record.msg) for record in caplog.records)


def mailing_row(mailing_id: int) -> Mailing:
    with session_scope() as session:
        return session.get(Mailing, mailing_id)


def deliveries(mailing_id: int) -> list[Delivery]:
    with session_scope() as session:
        return list(
            session.scalars(
                select(Delivery).where(Delivery.mailing_id == mailing_id).order_by(Delivery.id)
            )
        )


def fan_mails(email: FakeEmailClient):
    return [mail for mail in email.sent if mail.to != CREATOR_MAIL]


def run_to_preview(world) -> tuple[FakeEmailClient, FakeYouTubeConnector]:
    email, youtube = install()
    worker.run_tick(SENTIMENT_AT)
    worker.run_tick(PREVIEW_AT)
    assert mailing_row(world["mailing"]).status == MailingStatus.PREVIEW_SENT
    return email, youtube


class TestTheWholeWay:
    def test_sentiment_then_preview_then_the_fans_exactly_once(self, world):
        add_fan(world["creator"], "fan@example.org")
        email, _ = install()

        worker.run_tick(SENTIMENT_AT - timedelta(minutes=1))
        assert mailing_row(world["mailing"]).status == MailingStatus.SCHEDULED

        worker.run_tick(SENTIMENT_AT)
        assert mailing_row(world["mailing"]).status == MailingStatus.SENTIMENT_READY
        with session_scope() as session:
            assert session.scalar(select(Analysis).where(Analysis.kind == AnalysisKind.SENTIMENT))

        worker.run_tick(PREVIEW_AT)
        preview = email.last
        assert preview.to == CREATOR_MAIL
        assert preview.text.startswith(
            "Diese Mail geht am Dienstag, 22. September, um 18:00 Uhr an 1 Abonnent."
        )
        assert preview.idempotency_key.startswith(f"preview/{world['mailing']}/stop-token-1/")
        assert "List-Unsubscribe" not in preview.headers
        assert "Wie die Community" in preview.html or "COMMUNITY" in preview.text

        worker.run_tick(T - timedelta(seconds=1))
        assert fan_mails(email) == []

        worker.run_tick(T)
        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.SENT
        assert row.recipient_count == 1
        [mail] = fan_mails(email)
        assert mail.to == "fan@example.org"
        assert mail.subject == "Pilotkanal: Warum Verwaltung so langsam ist"
        assert mail.from_.startswith("Pilotkanal via ")
        assert mail.headers["List-Unsubscribe"].endswith("/abmelden/unsub-fan@example.org>")
        assert mail.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert "/s/view-token" in mail.text
        assert "eingetragen hast" in mail.text
        assert "/m/" not in mail.html
        [delivery] = deliveries(world["mailing"])
        assert mail.idempotency_key == f"mailing/{world['mailing']}/{delivery.id}"

        worker.run_tick(T + timedelta(hours=1))
        assert len(fan_mails(email)) == 1

    def test_a_worker_down_across_t_still_gives_the_creator_a_full_hour(self, world):
        add_fan(world["creator"], "fan@example.org")
        email, _ = install()
        late = T + timedelta(hours=5)

        worker.run_tick(late)  # sentiment
        worker.run_tick(late)  # preview
        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.PREVIEW_SENT
        assert row.send_at == late + timedelta(hours=1)

        worker.run_tick(late + timedelta(minutes=59))
        assert fan_mails(email) == []

        worker.run_tick(late + timedelta(hours=1))
        assert len(fan_mails(email)) == 1

    def test_a_mailing_with_no_fans_is_sent_to_nobody(self, world):
        email, _ = run_to_preview(world)
        assert "noch keine bestätigten Abonnenten" in email.last.text

        worker.run_tick(T)

        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.SENT
        assert row.recipient_count == 0
        assert email.batches == []


class TestSentiment:
    def test_a_temporary_failure_early_is_retried(self, world):
        install(youtube=FakeYouTubeConnector(fail_with=TemporaryError("down")))

        worker.run_tick(SENTIMENT_AT)

        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.SCHEDULED
        assert row.attempts == 1

    def test_near_the_preview_it_gives_up_and_the_mail_goes_on_without(self, world):
        install(youtube=FakeYouTubeConnector(fail_with=TemporaryError("down")))

        # The next retry (five minutes) would land past the preview deadline.
        worker.run_tick(PREVIEW_AT - timedelta(minutes=4))

        assert mailing_row(world["mailing"]).status == MailingStatus.SENTIMENT_READY
        with session_scope() as session:
            assert (
                session.scalar(select(Analysis).where(Analysis.kind == AnalysisKind.SENTIMENT))
                is None
            )

    def test_a_spent_budget_skips_the_sentiment(self, world):
        install()
        with session_scope() as session:
            session.add(
                LLMCall(
                    creator_id=world["creator"],
                    purpose="summary",
                    model="fake",
                    prompt_version="v1",
                    cost_cents=100_000,
                    ok=True,
                    created_at=SENTIMENT_AT,
                )
            )

        worker.run_tick(SENTIMENT_AT)

        assert mailing_row(world["mailing"]).status == MailingStatus.SENTIMENT_READY

    def test_a_video_made_private_cancels_the_mailing(self, world):
        email, _ = install(
            youtube=FakeYouTubeConnector(items=[content_item(VIDEO, is_public=False)])
        )

        worker.run_tick(SENTIMENT_AT)

        assert mailing_row(world["mailing"]).status == MailingStatus.CANCELLED
        with session_scope() as session:
            assert session.scalar(select(Appearance.status)) == AppearanceStatus.UNAVAILABLE
        worker.run_tick(T)
        assert email.sent == []


class TestTheSend:
    def test_a_video_deleted_after_the_preview_is_not_sent(self, world):
        add_fan(world["creator"], "fan@example.org")
        email, youtube = run_to_preview(world)
        youtube.items.clear()

        worker.run_tick(T)

        assert mailing_row(world["mailing"]).status == MailingStatus.CANCELLED
        assert fan_mails(email) == []
        assert deliveries(world["mailing"]) == []

    def test_the_snapshot_holds_only_confirmed_unblocked_fans_of_this_creator(self, world):
        creator = world["creator"]
        wanted = add_fan(creator, "fan@example.org")
        add_fan(creator, "pending@example.org", status=SubscriptionStatus.PENDING)
        add_fan(creator, "left@example.org", status=SubscriptionStatus.UNSUBSCRIBED)
        add_fan(creator, "blocked@example.org", blocked_at=PUBLISHED, blocked_reason="bounce")
        add_fan(world["other"], "elsewhere@example.org")
        email, _ = run_to_preview(world)

        worker.run_tick(T)

        assert [d.subscription_id for d in deliveries(world["mailing"])] == [wanted]
        assert [mail.to for mail in fan_mails(email)] == ["fan@example.org"]

    def test_a_fan_who_confirms_after_the_snapshot_waits_for_the_next_mail(self, world):
        add_fan(world["creator"], "fan@example.org")
        late = add_fan(world["creator"], "late@example.org", status=SubscriptionStatus.PENDING)
        email, _ = run_to_preview(world)
        email.batch_fails_with = EmailTemporaryError("provider down")

        worker.run_tick(T)  # snapshot taken, the batch fails
        assert mailing_row(world["mailing"]).status == MailingStatus.SENDING
        with session_scope() as session:
            session.execute(
                update(Subscription)
                .where(Subscription.id == late)
                .values(status=SubscriptionStatus.CONFIRMED)
            )
        email.batch_fails_with = None

        worker.run_tick(T + timedelta(hours=1))

        assert len(deliveries(world["mailing"])) == 1
        assert [mail.to for mail in fan_mails(email)] == ["fan@example.org"]

    def test_a_fan_who_leaves_during_the_send_still_gets_this_one(self, world):
        # Owner decision 2026-09-18 (plan §20 question 9): the snapshot holds.
        leaving = add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)
        email.batch_fails_with = EmailTemporaryError("provider down")
        worker.run_tick(T)
        with session_scope() as session:
            session.execute(
                update(Subscription)
                .where(Subscription.id == leaving)
                .values(status=SubscriptionStatus.UNSUBSCRIBED, unsubscribed_at=T)
            )
        email.batch_fails_with = None

        worker.run_tick(T + timedelta(hours=1))

        assert [mail.to for mail in fan_mails(email)] == ["fan@example.org"]


class TestExactlyOnce:
    def fans(self, world, count: int) -> None:
        for number in range(count):
            add_fan(world["creator"], f"fan{number:03d}@example.org")

    def test_a_crash_after_the_first_batch_resumes_with_the_rest(self, world):
        self.fans(world, 150)
        email, _ = run_to_preview(world)
        email.batch_fails_with = EmailTemporaryError("provider down")
        email.batches_before_failure = 1

        worker.run_tick(T)
        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.SENDING
        assert row.attempts == 1
        assert sum(d.sent_at is not None for d in deliveries(world["mailing"])) == 100

        email.batch_fails_with = None
        worker.run_tick(row.next_attempt_at)

        assert mailing_row(world["mailing"]).status == MailingStatus.SENT
        addresses = [mail.to for mail in fan_mails(email)]
        assert len(addresses) == 150
        assert len(set(addresses)) == 150

    def test_a_lost_answer_resends_the_same_batch_under_the_same_key(self, world):
        self.fans(world, 3)
        email, _ = run_to_preview(world)
        email.batch_fails_with = EmailTemporaryError("timeout after delivery")
        email.lose_response = True

        worker.run_tick(T)  # the provider got it, we never heard back
        email.batch_fails_with = None
        worker.run_tick(mailing_row(world["mailing"]).next_attempt_at)

        first, second = email.batches
        assert [m.idempotency_key for m in first] == [m.idempotency_key for m in second]
        # Byte-identical: the provider sees a repeat and delivers nothing twice.
        assert first == second

    def test_a_second_send_waits_while_the_first_holds_the_lock(self, world):
        self.fans(world, 2)
        email, _ = run_to_preview(world)

        with get_engine().connect() as other_worker:
            other_worker.execute(text("SELECT pg_advisory_lock(:id)"), {"id": world["mailing"]})
            worker.run_tick(T)
            assert mailing_row(world["mailing"]).status == MailingStatus.PREVIEW_SENT
            assert fan_mails(email) == []
            other_worker.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": world["mailing"]})

        worker.run_tick(T)
        assert len(fan_mails(email)) == 2

    def test_the_lock_is_released_even_when_the_send_fails(self, world):
        self.fans(world, 1)
        email, _ = run_to_preview(world)
        email.batch_fails_with = EmailTemporaryError("down")
        worker.run_tick(T)

        with get_engine().connect() as probe:
            got = probe.execute(
                text("SELECT pg_try_advisory_lock(:id)"), {"id": world["mailing"]}
            ).scalar()
            probe.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": world["mailing"]})
        assert got is True

    def test_a_stop_between_loading_and_sending_wins(self, world, logs):
        self.fans(world, 2)
        email, _ = run_to_preview(world)

        class StopDuringRecheck(FakeYouTubeConnector):
            def item_details(self, external_ids):
                with session_scope() as other:
                    mailings.stop(other, "stop-token-1", T)
                return super().item_details(external_ids)

        install(email=email, youtube=StopDuringRecheck(items=[content_item(VIDEO)]))
        worker.run_tick(T)

        assert mailing_row(world["mailing"]).status == MailingStatus.STOPPED
        assert deliveries(world["mailing"]) == []
        assert fan_mails(email) == []
        assert logged(logs, "mailing.transition_lost")

    def test_a_postpone_during_the_preview_send_wins(self, world, logs):
        new_send_at = T + timedelta(hours=24)

        def postpone_meanwhile(mail):
            with session_scope() as other:
                mailings.postpone(other, "stop-token-1", T, new_send_at)

        install(email=FakeEmailClient(on_send=postpone_meanwhile))
        worker.run_tick(SENTIMENT_AT)
        worker.run_tick(PREVIEW_AT)

        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.SCHEDULED
        assert row.send_at == new_send_at
        assert row.stop_token != "stop-token-1"
        assert row.render_snapshot is None
        assert logged(logs, "mailing.transition_lost")


class TestPayloadFreeze:
    def test_changes_after_the_preview_do_not_reach_the_fans(self, world):
        subscription_id = add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)
        with session_scope() as session:
            mailing = session.get(Mailing, world["mailing"])
            appearance = session.get(Appearance, mailing.appearance_id)
            creator = session.get(Creator, world["creator"])
            render = mailings.compose(session, appearance, creator, get_settings())
            expected = render(
                session.get(Subscription, subscription_id), snapshot=mailing.render_snapshot
            )
            creator.greeting_text = "Ganz neuer Gruß"
            creator.email_variant = "teaser"

        worker.run_tick(T)

        [mail] = fan_mails(email)
        assert mail.html == expected.html
        assert mail.text == expected.text
        assert "Servus!" in mail.text
        assert "Ganz neuer Gruß" not in mail.text


class TestFailure:
    def test_a_refused_batch_fails_the_mailing_and_tells_the_creator_once(self, world):
        add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)
        email.batch_fails_with = EmailError("HTTP 422")

        worker.run_tick(T)
        worker.run_tick(T + timedelta(hours=1))

        assert mailing_row(world["mailing"]).status == MailingStatus.FAILED
        # The send had begun. Even here — the provider refused the batch — the
        # notice stays pessimistic: a crash between an accepted batch and the
        # commit that records it looks exactly the same from the outside, and
        # "niemand hat sie bekommen" is a claim we cannot take back.
        notices = [m for m in email.sent if m.subject == NOTICES[NoticeKind.SEND_FAILED].subject]
        assert len(notices) == 1
        assert notices[0].to == CREATOR_MAIL

    def test_an_exhausted_ladder_before_the_preview_says_nothing_went_out(self, world):
        email, _ = install(email=FakeEmailClient(fail_with=EmailTemporaryError("down")))
        worker.run_tick(SENTIMENT_AT)
        with session_scope() as session:
            session.execute(
                update(Mailing)
                .where(Mailing.id == world["mailing"])
                .values(attempts=MAX_ATTEMPTS - 1)
            )
        email.fail_with = None
        # The fake fails the preview itself once more, then notices go through.
        email.on_send = lambda mail: _fail_previews(mail)

        worker.run_tick(PREVIEW_AT)

        assert mailing_row(world["mailing"]).status == MailingStatus.FAILED
        assert [m.subject for m in email.sent] == [NOTICES[NoticeKind.PREVIEW_FAILED].subject]


class TestFailureRaces:
    def test_a_mailing_stopped_while_its_step_failed_is_not_reported_failed(self, world):
        def stop_then_refuse(mail):
            with session_scope() as other:
                mailings.stop(other, "stop-token-1", PREVIEW_AT)
            raise EmailError("HTTP 422")

        email, _ = install(email=FakeEmailClient(on_send=stop_then_refuse))
        worker.run_tick(SENTIMENT_AT)

        worker.run_tick(PREVIEW_AT)

        assert mailing_row(world["mailing"]).status == MailingStatus.STOPPED
        assert email.sent == []


def _fail_previews(mail):
    if mail.tags.get("kind") == "preview":
        raise EmailTemporaryError("still down")


@pytest.fixture
def client(world, monkeypatch):
    monkeypatch.setenv("BASE_URL", "http://testserver")
    get_settings.cache_clear()
    with TestClient(create_app(), follow_redirects=False) as client:
        yield client


def set_mailing(mailing_id: int, **values) -> None:
    with session_scope() as session:
        session.execute(update(Mailing).where(Mailing.id == mailing_id).values(**values))


class TestTheStopLink:
    def test_fetching_the_link_changes_nothing_and_names_the_mail(self, world, client):
        install()

        page = client.get("/m/stop-token-1/stoppen")

        assert page.status_code == 200
        assert mailing_row(world["mailing"]).status == MailingStatus.SCHEDULED
        assert "Warum Verwaltung so langsam ist" in page.text
        assert "Dienstag, 22. September, um 18:00 Uhr" in page.text
        assert '<form method="post" action="/m/stop-token-1/stoppen">' in page.text
        assert "<button" in page.text

    def test_the_button_stops_the_mail_and_nothing_goes_out(self, world, client):
        add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)

        page = client.post("/m/stop-token-1/stoppen")

        assert page.status_code == 200
        assert "<h1>Gestoppt</h1>" in page.text
        assert 'role="status"' in page.text
        worker.run_tick(T + timedelta(hours=1))
        assert mailing_row(world["mailing"]).status == MailingStatus.STOPPED
        assert fan_mails(email) == []

    def test_a_second_stop_says_it_was_already_stopped(self, world, client):
        install()
        client.post("/m/stop-token-1/stoppen")

        page = client.post("/m/stop-token-1/stoppen")

        assert "bereits gestoppt" in page.text
        assert "<h1>Gestoppt</h1>" not in page.text

    @pytest.mark.parametrize(
        ("state", "says"),
        [
            (MailingStatus.SENDING, "schon unterwegs"),
            (MailingStatus.SENT, "schon verschickt"),
            (MailingStatus.CANCELLED, "nicht mehr öffentlich"),
            (MailingStatus.FAILED, "nicht rausgegangen"),
        ],
    )
    def test_a_mail_past_stopping_never_claims_to_be_stopped(self, world, client, state, says):
        install()
        set_mailing(world["mailing"], status=state)

        page = client.post("/m/stop-token-1/stoppen")

        assert page.status_code == 409
        assert says in page.text
        assert "<h1>Gestoppt</h1>" not in page.text
        assert 'role="alert"' in page.text
        assert mailing_row(world["mailing"]).status == state

    def test_an_unknown_link_points_to_the_newer_preview(self, world, client):
        page = client.get("/m/not-a-token/stoppen")

        assert page.status_code == 410
        assert "neuere Vorschau" in page.text


class TestThePostponeLink:
    def test_the_page_names_the_new_time_and_changes_nothing(self, world, client):
        install()

        page = client.get("/m/stop-token-1/verschieben")

        assert "Mittwoch, 23. September, um 18:00 Uhr" in page.text
        assert mailing_row(world["mailing"]).send_at == T

    def test_postponing_shifts_rotates_and_starts_over(self, world, client):
        add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)
        llm = fakes.FakeLLMGateway()
        install(email=email, llm=llm)

        page = client.post("/m/stop-token-1/verschieben")

        assert "<h1>Verschoben</h1>" in page.text
        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.SCHEDULED
        assert row.send_at == T + timedelta(hours=24)
        assert row.stop_token != "stop-token-1"
        assert row.render_snapshot is None
        with session_scope() as session:
            # SQL NULL, not a stored JSON "null": otherwise `IS NULL` misses it.
            assert session.execute(
                text("SELECT render_snapshot IS NULL FROM mailings WHERE id = :id"),
                {"id": world["mailing"]},
            ).scalar()
        # The old links are dead.
        assert client.get("/m/stop-token-1/stoppen").status_code == 410

        worker.run_tick(T)  # the old send time: nothing happens
        assert fan_mails(email) == []

        new_t = T + timedelta(hours=24)
        worker.run_tick(new_t - timedelta(hours=2))
        assert len(llm.calls) == 1  # the sentiment is fetched again
        worker.run_tick(new_t - timedelta(hours=1))
        assert email.last.idempotency_key.startswith(
            f"preview/{world['mailing']}/{row.stop_token}/"
        )
        worker.run_tick(new_t)
        assert [mail.to for mail in fan_mails(email)] == ["fan@example.org"]

    def test_past_the_cap_only_stopping_is_offered(self, world, client):
        install()
        cap = PUBLISHED + timedelta(hours=get_settings().schedule.max_delay_hours)
        set_mailing(world["mailing"], send_at=cap)

        page = client.get("/m/stop-token-1/verschieben")
        refused = client.post("/m/stop-token-1/verschieben")

        assert "Verschieben geht nicht mehr" in page.text
        assert 'action="/m/stop-token-1/stoppen"' in page.text
        assert 'action="/m/stop-token-1/verschieben"' not in page.text
        assert "Verschieben geht nicht mehr" in refused.text
        assert mailing_row(world["mailing"]).send_at == cap

    def test_a_preview_past_the_cap_has_no_postpone_link(self, world):
        with session_scope() as session:
            session.execute(update(Appearance).values(published_at=T - timedelta(days=30)))
        email, _ = run_to_preview(world)

        assert "/verschieben" not in email.last.html


def run_cleanup() -> None:
    with session_scope() as session:
        steps.cleanup(session, T, get_settings())


def appearance_status(external_id: str = VIDEO) -> str:
    with session_scope() as session:
        return session.scalar(
            select(Appearance.status).where(Appearance.external_id == external_id)
        )


class TestTheDailyRecheck:
    def test_a_sent_video_made_private_goes_and_its_page_answers_410(self, world, client):
        set_mailing(world["mailing"], status=MailingStatus.SENT)
        install(youtube=FakeYouTubeConnector(items=[content_item(VIDEO, is_public=False)]))

        run_cleanup()

        assert appearance_status() == AppearanceStatus.UNAVAILABLE
        assert mailing_row(world["mailing"]).status == MailingStatus.SENT
        assert client.get("/s/view-token").status_code == 410

    def test_a_deleted_back_catalogue_video_goes_too(self, world):
        with session_scope() as session:
            source_id = session.scalar(select(Source.id))
            session.add(
                Appearance(
                    source_id=source_id,
                    external_id="bbbbbbbbbbb",
                    title="Altes Video",
                    url="https://www.youtube.com/watch?v=bbbbbbbbbbb",
                    published_at=PUBLISHED - timedelta(days=300),
                    status=AppearanceStatus.ANALYZED,
                    is_backfill=True,
                    view_token="old-view-token",
                )
            )
        install()  # knows only VIDEO: the old one is absent, i.e. deleted

        run_cleanup()

        assert appearance_status("bbbbbbbbbbb") == AppearanceStatus.UNAVAILABLE
        assert appearance_status() == AppearanceStatus.ANALYZED

    def test_an_open_mailing_of_a_gone_video_is_cancelled(self, world):
        # The answer knows other videos, just not ours: that is what deleted
        # looks like. An answer that knows none at all is not believed.
        install(youtube=FakeYouTubeConnector(items=[content_item("otherrrrrrr")]))

        run_cleanup()

        assert mailing_row(world["mailing"]).status == MailingStatus.CANCELLED

    def test_a_youtube_outage_costs_the_recheck_not_the_deletions(self, world):
        pending = add_fan(world["creator"], "old@example.org", status=SubscriptionStatus.PENDING)
        with session_scope() as session:
            session.execute(
                update(Subscription)
                .where(Subscription.id == pending)
                .values(confirm_expires_at=T - timedelta(days=1))
            )
        install(youtube=FakeYouTubeConnector(fail_with=TemporaryError("down")))

        run_cleanup()

        assert appearance_status() == AppearanceStatus.ANALYZED
        with session_scope() as session:
            assert session.get(Subscription, pending) is None


YOUTUBE_KEY = NeedsOperator("YouTube Data API", "API key rejected", "check YOUTUBE_API_KEY")


def operator_logs(caplog) -> list[str]:
    return [
        str(record.msg)
        for record in caplog.records
        if "operator.action_needed" in str(record.msg) and record.levelname == "ERROR"
    ]


class TestARejectedKeyNeverCostsAVideo:
    """Only the operator can fix a key or a plan; the rows wait, loudly, for them."""

    def test_an_appearance_waits_without_counting_an_attempt(self, world, logs):
        with session_scope() as session:
            session.add(
                Appearance(
                    source_id=session.scalar(select(Source.id)),
                    external_id="nnnnnnnnnnn",
                    title="Neu",
                    url="https://www.youtube.com/watch?v=nnnnnnnnnnn",
                    published_at=T,
                    status=AppearanceStatus.DETECTED,
                    view_token="new-view-token",
                )
            )
        email, _ = install(youtube=FakeYouTubeConnector(fail_with=YOUTUBE_KEY))

        worker.run_tick(T)

        with session_scope() as session:
            row = session.scalar(select(Appearance).where(Appearance.external_id == "nnnnnnnnnnn"))
            assert row.status == AppearanceStatus.DETECTED
            assert row.attempts == 0
            assert row.next_attempt_at == T + timedelta(hours=1)
            assert "YOUTUBE_API_KEY" in row.last_error
        assert email.sent == []  # the creator has nothing to do with it
        assert any("YOUTUBE_API_KEY" in line for line in operator_logs(logs))

    def test_a_send_on_an_exhausted_plan_waits_and_never_fails(self, world, logs):
        add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)
        email.batch_fails_with = QuotaExhausted("Resend", "sending plan exhausted", "upgrade")

        for hour in range(MAX_ATTEMPTS + 2):
            worker.run_tick(T + timedelta(hours=hour))

        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.SENDING
        assert row.attempts == 0
        assert fan_mails(email) == []
        assert not [m for m in email.sent if m.tags.get("kind") == "notice"]
        assert operator_logs(logs)

    def test_the_sentiment_step_goes_on_without_and_says_why(self, world, logs):
        llm = fakes.FakeLLMGateway(
            raises=NeedsOperator("LLM gateway", "no keys", "ANTHROPIC_API_KEY")
        )
        install(llm=llm)

        worker.run_tick(SENTIMENT_AT)

        assert mailing_row(world["mailing"]).status == MailingStatus.SENTIMENT_READY
        assert any("ANTHROPIC_API_KEY" in line for line in operator_logs(logs))


NUL = "Ein \x00 Byte, das Postgres ablehnt"


class TestAFailureInsideAStepNeverLosesWhatWasPaidFor:
    """A caught database error leaves the transaction aborted — and the commit
    that follows reports success while discarding every write. Anything a step
    has already paid for must be committed before it risks another statement.
    """

    def add_transcribed_video(self) -> int:
        with session_scope() as session:
            appearance = Appearance(
                source_id=session.scalar(select(Source.id)),
                external_id="ppppppppppp",
                title="Backfill-Video",
                url="https://www.youtube.com/watch?v=ppppppppppp",
                published_at=PUBLISHED - timedelta(days=200),
                duration_seconds=900,
                status=AppearanceStatus.TRANSCRIBED,
                is_backfill=True,
                view_token="poison-view-token",
            )
            session.add(appearance)
            session.flush()
            session.add(
                Transcript(
                    appearance_id=appearance.id,
                    origin="youtube_unofficial",
                    language="de",
                    is_generated=True,
                    fetched_at=T,
                    segments=[{"start": 0.0, "duration": 3.0, "text": "Hallo."}],
                )
            )
            return appearance.id

    def poisoned_llm(self) -> fakes.FakeLLMGateway:
        """Answers with a summary, then with a sentiment Postgres will refuse."""
        sentiment = Sentiment(
            overall=NUL, agreed=[], disagreed=[], questions=[], comment_count_used=1
        )
        return fakes.FakeLLMGateway(results=[_default_for(Summary), sentiment])

    def test_the_summary_survives_a_sentiment_the_database_refuses(self, world):
        appearance_id = self.add_transcribed_video()
        install(llm=self.poisoned_llm(), youtube=FakeYouTubeConnector(comments=COMMENTS))

        worker.run_tick(T)

        with session_scope() as session:
            stored = session.get(Appearance, appearance_id)
            assert stored.status == AppearanceStatus.ANALYZED
            assert session.scalar(
                select(Analysis).where(
                    Analysis.appearance_id == appearance_id,
                    Analysis.kind == AnalysisKind.SUMMARY,
                )
            )

    def test_a_mailing_is_not_failed_by_a_sentiment_the_database_refuses(self, world):
        install(
            llm=self.poisoned_llm(),
            youtube=FakeYouTubeConnector(items=[content_item(VIDEO)], comments=COMMENTS),
        )

        worker.run_tick(SENTIMENT_AT)

        # The comment box is a bonus; the mail goes on without it.
        assert mailing_row(world["mailing"]).status == MailingStatus.SENTIMENT_READY


class TestTheSendCommitsWhatItFinished:
    """The lock is held for the whole send; whatever it decided must survive it."""

    def test_sent_is_committed_before_the_lock_is_released(self, world):
        add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)

        with session_scope() as session:
            steps.send(session, world["mailing"], T)
            session.rollback()  # the caller's transaction is lost

        assert mailing_row(world["mailing"]).status == MailingStatus.SENT
        assert len(fan_mails(email)) == 1

    def test_an_unlock_that_fails_does_not_undo_a_finished_send(self, world, logs, monkeypatch):
        add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)
        engine = get_engine()

        class UnlockRefuses:
            """A connection that sends, but cannot give the lock back."""

            def __init__(self, real):
                self._real = real

            def execute(self, statement, *args, **kwargs):
                if "unlock" in str(statement):
                    raise OperationalError("server closed the connection", None, Exception())
                return self._real.execute(statement, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._real, name)

        monkeypatch.setattr(
            mailings,
            "get_engine",
            lambda: SimpleNamespace(connect=lambda: UnlockRefuses(engine.connect())),
        )

        worker.run_tick(T)

        assert mailing_row(world["mailing"]).status == MailingStatus.SENT
        assert len(fan_mails(email)) == 1
        assert not [m for m in email.sent if m.tags.get("kind") == "notice"]
        assert logged(logs, "mailing.unlock_failed")


class TestTheDailyJobProtectsTheDeletions:
    """Retention protects privacy; a video platform must never hold it up."""

    def expired_sign_up(self, world) -> int:
        pending = add_fan(world["creator"], "old@example.org", status=SubscriptionStatus.PENDING)
        with session_scope() as session:
            session.execute(
                update(Subscription)
                .where(Subscription.id == pending)
                .values(confirm_expires_at=T - timedelta(days=1))
            )
        return pending

    def test_a_re_check_that_fails_midway_keeps_the_deletions(self, world):
        pending = self.expired_sign_up(world)

        class GoneThenBroken(FakeYouTubeConnector):
            def item_details(self, external_ids):
                return []  # every video looks gone …

        install(youtube=GoneThenBroken())
        with session_scope() as session:
            try:
                steps.cleanup(session, T, get_settings())
            finally:
                session.rollback()  # … and the rest of the job is lost

        with session_scope() as session:
            assert session.get(Subscription, pending) is None

    def test_an_answer_that_knows_no_video_at_all_is_not_taken_as_proof(self, world, logs):
        # One odd 200 from the API must not retire every summary page there is.
        with session_scope() as session:
            source_id = session.scalar(select(Source.id))
            for number in range(steps.TOO_MANY_TO_LOSE_AT_ONCE):
                session.add(
                    Appearance(
                        source_id=source_id,
                        external_id=f"many{number:07d}",
                        title=f"Video {number}",
                        url="https://www.youtube.com/watch?v=x",
                        published_at=PUBLISHED,
                        status=AppearanceStatus.ANALYZED,
                        view_token=f"token-{number}",
                    )
                )
        install(youtube=FakeYouTubeConnector(items=[]))

        run_cleanup()

        assert appearance_status() == AppearanceStatus.ANALYZED
        assert mailing_row(world["mailing"]).status == MailingStatus.SCHEDULED
        assert logged(logs, "cleanup.recheck_failed")

    def test_a_quota_that_ran_out_is_reported_as_the_operators(self, world, logs):
        install(youtube=FakeYouTubeConnector(fail_with=YOUTUBE_KEY))

        run_cleanup()

        assert any("YOUTUBE_API_KEY" in line for line in operator_logs(logs))


class TestALongSendDoesNotGiveUpOnItself:
    def test_a_batch_that_went_through_clears_the_failures_before_it(self, world):
        for number in range(150):
            add_fan(world["creator"], f"fan{number:03d}@example.org")
        email, _ = run_to_preview(world)
        email.batch_fails_with = EmailTemporaryError("provider hiccup")
        worker.run_tick(T)  # the send has begun and stumbled once
        assert mailing_row(world["mailing"]).status == MailingStatus.SENDING

        # Nine hiccups have happened over this long list by now; the tenth
        # would end the mailing with most of the list unsent.
        set_mailing(world["mailing"], attempts=MAX_ATTEMPTS - 1)
        email.batches_before_failure = 1  # one batch goes through, then it fails again
        worker.run_tick(T + timedelta(hours=1))

        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.SENDING  # not failed: a batch got through
        assert row.attempts == 1  # progress cleared what came before it

        email.batch_fails_with = None
        worker.run_tick(row.next_attempt_at)

        assert mailing_row(world["mailing"]).status == MailingStatus.SENT
        assert len(fan_mails(email)) == 150


class TestABlockDuringTheSendIsHonoured:
    """A bounce or a spam complaint mid-send stops the remaining batches —
    the provider would drop the mail anyway and the complaint costs every
    creator on the platform (owner decision 2026-09-20)."""

    def test_a_fan_blocked_mid_send_gets_no_further_batch(self, world):
        staying = add_fan(world["creator"], "fan@example.org")
        blocked = add_fan(world["creator"], "complains@example.org")
        email, _ = run_to_preview(world)
        email.batch_fails_with = EmailTemporaryError("provider down")

        worker.run_tick(T)  # snapshot taken, nothing delivered yet
        with session_scope() as session:
            session.execute(
                update(Subscriber)
                .where(Subscriber.email == "complains@example.org")
                .values(blocked_at=T, blocked_reason="complaint")
            )
        email.batch_fails_with = None

        worker.run_tick(T + timedelta(hours=1))

        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.SENT
        assert [mail.to for mail in fan_mails(email)] == ["fan@example.org"]
        assert row.recipient_count == 1  # counts what was sent, not what was planned
        sent = {d.subscription_id: d.sent_at for d in deliveries(world["mailing"])}
        assert sent[staying] is not None
        assert sent[blocked] is None  # the ledger says: never sent


class TestThePreviewSurvivesARetry:
    """Its idempotency key must never meet a changed body: what the provider
    does with that is undocumented (plan §18), and this design never asks."""

    def test_the_send_time_is_written_before_the_preview_goes_out(self, world):
        install(email=FakeEmailClient(fail_with=EmailTemporaryError("timeout")))

        worker.run_tick(SENTIMENT_AT)
        worker.run_tick(PREVIEW_AT + timedelta(minutes=1))  # a late tick pushes the send

        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.SENTIMENT_READY  # the preview failed
        assert row.send_at == PREVIEW_AT + timedelta(minutes=1) + timedelta(hours=1)

    def test_the_same_preview_twice_is_one_mail_for_the_provider(self, world):
        install()
        worker.run_tick(SENTIMENT_AT)
        attempts = []

        def record_and_fail(mail):
            attempts.append(mail)
            if len(attempts) == 1:
                raise EmailTemporaryError("the answer never arrived")

        install(email=FakeEmailClient(on_send=record_and_fail))
        # The same clock: nothing about the mail has changed between the two.
        worker.run_tick(PREVIEW_AT)
        set_mailing(world["mailing"], next_attempt_at=None)
        worker.run_tick(PREVIEW_AT)

        first, second = attempts
        assert first.html == second.html
        assert first.idempotency_key == second.idempotency_key

    def test_a_later_attempt_that_says_something_else_says_it_under_its_own_key(self, world):
        # A late retry pushes the send time, so the mail announces a new one.
        # That is a different mail, and it must not travel under the old key.
        install()
        worker.run_tick(SENTIMENT_AT)
        attempts = []

        def record_and_fail(mail):
            attempts.append(mail)
            if len(attempts) == 1:
                raise EmailTemporaryError("the answer never arrived")

        install(email=FakeEmailClient(on_send=record_and_fail))
        worker.run_tick(PREVIEW_AT)
        worker.run_tick(mailing_row(world["mailing"]).next_attempt_at)

        first, second = attempts
        assert first.html != second.html
        assert first.idempotency_key != second.idempotency_key

    def test_the_key_carries_the_mailing_its_token_and_its_content(self, world):
        add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)

        key = email.last.idempotency_key
        mailing, token = world["mailing"], mailing_row(world["mailing"]).stop_token

        assert key.startswith(f"preview/{mailing}/{token}/")
        assert len(key.rsplit("/", 1)[1]) == 12


class TestTheFailureNoticeTellsTheTruth:
    def test_a_mailing_that_never_started_sending_says_nothing_went_out(self, world):
        add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)
        # YouTube is down at send time, so the send never begins.
        install(email=email, youtube=FakeYouTubeConnector(fail_with=TemporaryError("down")))
        set_mailing(world["mailing"], attempts=MAX_ATTEMPTS - 1)

        worker.run_tick(T)

        assert mailing_row(world["mailing"]).status == MailingStatus.FAILED
        assert deliveries(world["mailing"]) == []
        [notice] = [m for m in email.sent if m.tags.get("kind") == "notice"]
        assert notice.subject == NOTICES[NoticeKind.NOT_SENT].subject


class TestAMailingDoesNotWaitForever:
    """Parking is right for a video; a mailing has a promise attached to it.

    The creator was shown a preview naming a time. If we cannot send around
    that time, they have to hear about it instead of a silence that lasts
    until somebody notices the log.
    """

    def test_a_key_problem_at_send_time_ends_the_mailing_after_the_grace_period(self, world):
        add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)
        install(email=email, youtube=FakeYouTubeConnector(fail_with=YOUTUBE_KEY))

        worker.run_tick(T)
        assert mailing_row(world["mailing"]).status == MailingStatus.PREVIEW_SENT  # parked

        worker.run_tick(T + worker.GIVE_UP_ON_A_MAILING_AFTER + timedelta(minutes=1))

        assert mailing_row(world["mailing"]).status == MailingStatus.FAILED
        assert [m.subject for m in email.sent if m.tags.get("kind") == "notice"] == [
            NOTICES[NoticeKind.NOT_SENT].subject
        ]

    def test_inside_the_grace_period_it_keeps_trying(self, world):
        add_fan(world["creator"], "fan@example.org")
        email, _ = run_to_preview(world)
        install(email=email, youtube=FakeYouTubeConnector(fail_with=YOUTUBE_KEY))

        worker.run_tick(T)
        worker.run_tick(T + timedelta(hours=1))

        row = mailing_row(world["mailing"])
        assert row.status == MailingStatus.PREVIEW_SENT
        assert row.attempts == 0  # a key problem still costs no attempt
