"""Recording an upload and deciding whether it is worth summarising."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.db.models import Appearance, AppearanceStatus, Creator, SkipReason, Source, SourceKind
from app.jobs import steps
from app.services import set_services
from tests import fakes
from tests.fakes import FakeYouTubeConnector, content_item

pytestmark = pytest.mark.integration

ONBOARDED = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
CHANNEL = "UCpilot0000000000000000"


@pytest.fixture
def source(session):
    creator = Creator(slug="pilot", name="Pilotkanal", contact_email="pilot@example.org")
    session.add(creator)
    session.flush()
    source = Source(
        creator_id=creator.id, kind=SourceKind.YOUTUBE, external_id=CHANNEL, created_at=ONBOARDED
    )
    session.add(source)
    session.flush()
    return source


def ingest(session, source, video_id, published_at, **kwargs):
    return steps.ingest_item(
        session,
        source,
        external_id=video_id,
        title="Ein Video",
        url=f"https://www.youtube.com/watch?v={video_id}",
        published_at=published_at,
        **kwargs,
    )


def enrich_with(session, appearance, items):
    set_services(fakes.services(youtube=FakeYouTubeConnector(items=items)))
    steps.enrich(session, appearance.id, NOW)
    session.flush()
    session.refresh(appearance)


class TestIngestIdempotency:
    def test_the_same_video_twice_yields_one_row(self, session, source, fake_services):
        # The unique constraint is the guarantee, not application logic: this
        # must hold however two calls interleave.
        first = ingest(session, source, "aaaaaaaaaaa", NOW)
        second = ingest(session, source, "aaaaaaaaaaa", NOW)

        assert first is not None
        assert second is None
        assert session.scalar(select(func.count()).select_from(Appearance)) == 1

    def test_every_appearance_gets_its_own_view_token(self, session, source, fake_services):
        first = ingest(session, source, "aaaaaaaaaaa", NOW)
        second = ingest(session, source, "bbbbbbbbbbb", NOW)

        assert first.view_token != second.view_token
        assert len(first.view_token) >= 43  # 256 bits, url-safe


class TestBacklog:
    def test_a_poll_never_ingests_the_back_catalogue(self, session, source, fake_services):
        # Otherwise the first poll would mail years of archive to the new list.
        published_before_onboarding = ONBOARDED - timedelta(days=300)

        assert ingest(session, source, "ccccccccccc", published_before_onboarding) is None

    def test_a_backfill_ingests_it_and_marks_it(self, session, source, fake_services):
        appearance = ingest(
            session, source, "ccccccccccc", ONBOARDED - timedelta(days=300), allow_backlog=True
        )

        assert appearance.is_backfill is True

    def test_an_upload_after_onboarding_is_never_backfill(self, session, source, fake_services):
        appearance = ingest(
            session, source, "aaaaaaaaaaa", ONBOARDED + timedelta(days=1), allow_backlog=True
        )

        assert appearance.is_backfill is False


class TestEnrich:
    def test_a_long_public_video_moves_on(self, session, source, fake_services):
        appearance = ingest(session, source, "aaaaaaaaaaa", NOW)

        enrich_with(session, appearance, [content_item("aaaaaaaaaaa", duration_seconds=1421)])

        assert appearance.status == AppearanceStatus.ENRICHED
        assert appearance.duration_seconds == 1421

    def test_a_short_is_dropped_for_good(self, session, source, fake_services):
        appearance = ingest(session, source, "bbbbbbbbbbb", NOW)

        enrich_with(session, appearance, [content_item("bbbbbbbbbbb", duration_seconds=41)])

        assert appearance.status == AppearanceStatus.SKIPPED_SHORT

    def test_a_deleted_video_becomes_unavailable(self, session, source, fake_services):
        appearance = ingest(session, source, "gonegonegon", NOW)

        enrich_with(session, appearance, [])  # the id is simply absent

        assert appearance.status == AppearanceStatus.UNAVAILABLE

    def test_the_authoritative_title_replaces_the_feeds_provisional_one(
        self, session, source, fake_services
    ):
        appearance = ingest(session, source, "aaaaaaaaaaa", NOW)

        enrich_with(session, appearance, [content_item("aaaaaaaaaaa", title="Der echte Titel")])

        assert appearance.title == "Der echte Titel"


class TestEnrichWaitsInsteadOfGivingUp:
    def test_an_upcoming_premiere_stays_and_is_checked_again(self, session, source, fake_services):
        appearance = ingest(session, source, "ddddddddddd", NOW)

        enrich_with(session, appearance, [content_item("ddddddddddd", is_live_or_upcoming=True)])

        assert appearance.status == AppearanceStatus.DETECTED
        assert appearance.skip_reason == SkipReason.NOT_PUBLIC_YET
        assert appearance.next_attempt_at == NOW + timedelta(hours=6)

    def test_waiting_for_the_world_costs_no_attempt(self, session, source, fake_services):
        # A premiere three weeks out must still be waiting when it starts;
        # counting attempts would give it up after a day.
        appearance = ingest(session, source, "ddddddddddd", NOW)

        enrich_with(session, appearance, [content_item("ddddddddddd", is_live_or_upcoming=True)])

        assert appearance.attempts == 0

    def test_a_private_video_waits_too(self, session, source, fake_services):
        appearance = ingest(session, source, "fffffffffff", NOW)

        enrich_with(session, appearance, [content_item("fffffffffff", is_public=False)])

        assert appearance.status == AppearanceStatus.DETECTED

    @pytest.mark.parametrize("duration", [0, None])
    def test_an_unknown_duration_waits_and_is_never_called_short(
        self, session, source, fake_services, duration
    ):
        # A just-finished livestream reports PT0S while it is being processed.
        # Treating that as "shorter than five minutes" would silently bin the
        # recording, terminally and without telling anyone.
        appearance = ingest(session, source, "eeeeeeeeeee", NOW)

        enrich_with(session, appearance, [content_item("eeeeeeeeeee", duration_seconds=duration)])

        assert appearance.status == AppearanceStatus.DETECTED
        assert appearance.skip_reason == SkipReason.NO_DURATION_YET
        assert appearance.attempts == 0


class TestPremiereScheduledBeforeOnboarding:
    def test_going_live_after_onboarding_clears_the_backfill_flag(
        self, session, source, fake_services
    ):
        # Announced before the creator signed up, broadcast afterwards. The feed
        # date says "archive", the real start time says "new upload" — and this
        # is typically the newest playlist entry, so the backfill picks it up.
        # Without re-evaluating the flag it would get a page and never a mail.
        appearance = ingest(
            session, source, "eeeeeeeeeee", ONBOARDED - timedelta(days=5), allow_backlog=True
        )
        assert appearance.is_backfill is True

        enrich_with(
            session,
            appearance,
            [content_item("eeeeeeeeeee", published_at=ONBOARDED + timedelta(days=9))],
        )

        assert appearance.is_backfill is False
        assert appearance.status == AppearanceStatus.ENRICHED

    def test_real_back_catalogue_keeps_the_flag(self, session, source, fake_services):
        old = ONBOARDED - timedelta(days=300)
        appearance = ingest(session, source, "ccccccccccc", old, allow_backlog=True)

        enrich_with(session, appearance, [content_item("ccccccccccc", published_at=old)])

        assert appearance.is_backfill is True

    def test_the_delay_counts_from_go_live(self, session, source, fake_services):
        went_live = ONBOARDED + timedelta(days=9)
        appearance = ingest(
            session, source, "eeeeeeeeeee", ONBOARDED - timedelta(days=5), allow_backlog=True
        )

        enrich_with(session, appearance, [content_item("eeeeeeeeeee", published_at=went_live)])

        assert appearance.published_at == went_live
