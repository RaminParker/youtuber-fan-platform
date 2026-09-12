"""The summarize step: the analysis, the ledger, the cap, and the plan to send."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.analysis.summarize import TranscriptTooLong
from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import (
    Analysis,
    AnalysisKind,
    Appearance,
    AppearanceStatus,
    Creator,
    LLMCall,
    Mailing,
    MailingStatus,
    Source,
    SourceKind,
    Transcript,
)
from app.errors import CostCapExceeded
from app.jobs import steps
from app.services import set_services
from tests import fakes
from tests.fakes import FakeEmailClient, FakeLLMGateway, FakeYouTubeConnector

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
ONBOARDED = datetime(2026, 9, 1, tzinfo=UTC)
PUBLISHED = datetime(2026, 9, 10, 18, 0, tzinfo=UTC)


# The ledger commits in a session of its own — that independence is the whole
# point of it — so these tests have to commit too, and are cleaned up by
# `committed_database` afterwards.


@pytest.fixture
def session(committed_database):
    """A committing session, not the rolled-back one the other tests use."""
    with session_scope() as committing:
        yield committing


@pytest.fixture
def appearance(session):
    creator = Creator(slug="pilot", name="Pilotkanal", contact_email="pilot@example.org")
    session.add(creator)
    session.commit()
    source = Source(
        creator_id=creator.id,
        kind=SourceKind.YOUTUBE,
        external_id="UCpilot0000000000000000",
        created_at=ONBOARDED,
    )
    session.add(source)
    session.commit()
    appearance = Appearance(
        source_id=source.id,
        external_id="aaaaaaaaaaa",
        title="Warum Verwaltung so langsam ist",
        url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
        published_at=PUBLISHED,
        duration_seconds=1421,
        status=AppearanceStatus.TRANSCRIBED,
        view_token="view-token",
    )
    session.add(appearance)
    session.commit()
    session.add(
        Transcript(
            appearance_id=appearance.id,
            origin="youtube_unofficial",
            language="de",
            is_generated=True,
            fetched_at=NOW,
            segments=[
                {"start": 0.0, "duration": 3.5, "text": "Guten Abend und willkommen."},
                {"start": 61.0, "duration": 4.0, "text": "Zuständigkeiten sind zersplittert."},
            ],
        )
    )
    session.commit()
    return appearance


def run(session, appearance, *, llm=None, youtube=None, email=None):
    gateway = llm or FakeLLMGateway()
    set_services(
        fakes.services(
            llm=gateway, youtube=youtube or FakeYouTubeConnector(), email=email or FakeEmailClient()
        )
    )
    steps.summarize(session, appearance.id, NOW)
    session.commit()
    session.refresh(appearance)
    return gateway


class TestTheSummary:
    def test_it_is_stored_with_what_produced_it(self, session, appearance, fake_services):
        run(session, appearance)

        analysis = session.scalar(select(Analysis).where(Analysis.kind == AnalysisKind.SUMMARY))
        assert analysis.prompt_version == "v1"
        assert analysis.model == "anthropic/claude-sonnet-4-5"
        assert analysis.content["headline"]
        assert appearance.status == AppearanceStatus.ANALYZED

    def test_the_transcript_reaches_the_model_with_timestamps(
        self, session, appearance, fake_services
    ):
        # Those markers are the only timestamps the model may use, and they
        # become the jump links into the video.
        gateway = run(session, appearance)

        assert "[01:01] Zuständigkeiten sind zersplittert." in gateway.calls[0]["user"]

    def test_the_prompt_rules_travel_as_the_system_message(
        self, session, appearance, fake_services
    ):
        gateway = run(session, appearance)

        assert "clickbait" in gateway.calls[0]["system"]

    def test_running_it_twice_replaces_the_analysis_rather_than_duplicating_it(
        self, session, appearance, fake_services
    ):
        # One current analysis per kind: a refreshed sentiment overwrites the
        # stale one instead of accumulating beside it. Uses a back catalogue
        # item so the run creates no mailing, which could only happen once.
        appearance.is_backfill = True
        session.commit()
        run(session, appearance)
        appearance.status = AppearanceStatus.TRANSCRIBED
        session.commit()

        run(session, appearance)

        assert session.scalar(select(func.count()).select_from(Analysis)) == 1

    def test_one_item_can_never_acquire_a_second_mailing(self, session, appearance, fake_services):
        # The unique constraint is the guarantee, not application logic.
        from sqlalchemy.exc import IntegrityError

        run(session, appearance)
        appearance.status = AppearanceStatus.TRANSCRIBED
        session.commit()

        with pytest.raises(IntegrityError):
            run(session, appearance)

        # A failed flush poisons the session; the fixture has to be able to close.
        session.rollback()


class TestTheMailing:
    def test_a_normal_upload_gets_one_planned_for_the_creators_delay(
        self, session, appearance, fake_services
    ):
        run(session, appearance)

        mailing = session.scalar(select(Mailing))
        assert mailing.status == MailingStatus.SCHEDULED
        assert mailing.send_at == PUBLISHED + timedelta(hours=168)
        assert mailing.stop_token

    def test_a_creators_own_delay_wins_over_the_default(self, session, appearance, fake_services):
        session.get(
            Creator, session.get(Source, appearance.source_id).creator_id
        ).send_delay_hours = 72
        session.commit()

        run(session, appearance)

        assert session.scalar(select(Mailing)).send_at == PUBLISHED + timedelta(hours=72)

    def test_a_back_catalogue_item_gets_no_mailing(self, session, appearance, fake_services):
        # Its page exists from day one; mailing the archive would not do.
        appearance.is_backfill = True
        session.commit()

        run(session, appearance)

        assert session.scalar(select(Mailing)) is None

    def test_but_it_does_get_its_sentiment_right_away(self, session, appearance, fake_services):
        # There is no send to wait for, and an old video's comments are final.
        appearance.is_backfill = True
        session.commit()
        comments = [
            fakes.Comment(
                text="Ein wirklich guter Punkt war das", like_count=9, author_channel_id="UCfan"
            )
        ]

        run(session, appearance, youtube=FakeYouTubeConnector(comments=comments))

        assert session.scalar(select(Analysis).where(Analysis.kind == AnalysisKind.SENTIMENT))

    def test_a_failing_sentiment_does_not_cost_the_summary(
        self, session, appearance, fake_services
    ):
        appearance.is_backfill = True
        session.commit()
        broken = FakeYouTubeConnector(fail_with=RuntimeError("comments unavailable"))

        run(session, appearance, youtube=broken)

        assert appearance.status == AppearanceStatus.ANALYZED


class TestTheLedger:
    def test_every_call_is_booked(self, session, appearance, fake_services):
        run(session, appearance)

        call = session.scalar(select(LLMCall))
        assert call.purpose == "summary"
        assert call.tokens_in == 5000
        assert call.ok is True
        assert call.cost_cents == Decimal("2.7000")

    def test_a_failed_call_is_booked_too(self, session, appearance, fake_services):
        # Otherwise a retry loop would spend money the ledger never sees.
        with pytest.raises(RuntimeError):
            run(session, appearance, llm=FakeLLMGateway(raises=RuntimeError("gateway down")))

        assert session.scalar(select(LLMCall)).ok is False

    def test_the_booking_survives_the_steps_rollback(self, session, appearance, fake_services):
        # The ledger commits in its own session, precisely so that a step which
        # pays and then fails cannot roll back the record of what it spent.
        with pytest.raises(RuntimeError):
            run(session, appearance, llm=FakeLLMGateway(raises=RuntimeError("boom")))

        assert session.scalar(select(func.count()).select_from(LLMCall)) == 1


class TestTheCap:
    def test_a_creator_over_budget_is_refused(self, session, appearance, fake_services):
        creator_id = session.get(Source, appearance.source_id).creator_id
        session.add(
            LLMCall(
                creator_id=creator_id,
                purpose="summary",
                model="m",
                prompt_version="v1",
                cost_cents=Decimal("600"),
                ok=True,
                created_at=NOW,
            )
        )
        session.commit()

        with pytest.raises(CostCapExceeded):
            run(session, appearance)

    def test_yesterdays_spending_does_not_count(self, session, appearance, fake_services):
        creator_id = session.get(Source, appearance.source_id).creator_id
        session.add(
            LLMCall(
                creator_id=creator_id,
                purpose="summary",
                model="m",
                prompt_version="v1",
                cost_cents=Decimal("600"),
                ok=True,
                created_at=NOW - timedelta(days=1),
            )
        )
        session.commit()

        run(session, appearance)

        assert appearance.status == AppearanceStatus.ANALYZED


class TestTooLong:
    def test_the_item_is_skipped_and_the_creator_told(self, session, appearance, fake_services):
        settings = get_settings()
        transcript = session.scalar(select(Transcript))
        transcript.segments = [{"start": 0.0, "duration": 1.0, "text": "x" * 200}] * (
            settings.content.max_transcript_chars // 200 + 10
        )
        session.commit()
        mailer = FakeEmailClient()

        run(session, appearance, email=mailer)

        assert appearance.status == AppearanceStatus.SKIPPED_TOO_LONG
        assert len(mailer.sent) == 1
        assert "zu lang" in mailer.last.subject

    def test_the_summariser_says_so_itself(self):
        from app.analysis.summarize import summarise
        from app.transcripts.base import Segment

        settings = get_settings()
        segments = [Segment(start=0.0, duration=1.0, text="x" * 1000)] * 1000

        with pytest.raises(TranscriptTooLong):
            summarise(FakeLLMGateway(), segments, title="t", channel="c", settings=settings)
