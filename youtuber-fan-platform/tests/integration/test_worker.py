"""The worker loop: picking due rows, and what happens when a step fails.

These tests let the code commit for real. The rolled-back session fixture
cannot serve here, because the behaviour under test *is* that each step commits
on its own and that the retry bookkeeping survives the step's rollback.
"""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app import worker
from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import (
    Appearance,
    AppearanceStatus,
    Creator,
    JobRun,
    Source,
    SourceKind,
)
from app.errors import TemporaryError
from app.jobs import steps
from app.jobs.schedule import MAX_ATTEMPTS, retry_at
from app.services import set_services
from app.sources.youtube.data_api import YouTubeError, YouTubeTemporaryError
from tests import fakes
from tests.fakes import FakeEmailClient, FakeYouTubeConnector, FlakyConnector, content_item

pytestmark = pytest.mark.integration

ONBOARDED = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)


@pytest.fixture
def pilot(committed_database):
    """A creator with a source, committed so the worker can find them."""
    with session_scope() as session:
        creator = Creator(slug="pilot", name="Pilotkanal", contact_email="pilot@example.org")
        session.add(creator)
        session.flush()
        session.add(
            Source(
                creator_id=creator.id,
                kind=SourceKind.YOUTUBE,
                external_id="UCpilot0000000000000000",
                created_at=ONBOARDED,
            )
        )
        session.flush()
        return creator.id


def add_appearance(video_id: str, status: str = AppearanceStatus.DETECTED, **kwargs) -> int:
    with session_scope() as session:
        source_id = session.scalars(select(Source.id)).one()
        appearance = Appearance(
            source_id=source_id,
            external_id=video_id,
            title="Ein Video",
            url=f"https://www.youtube.com/watch?v={video_id}",
            published_at=NOW - timedelta(days=1),
            status=status,
            view_token=f"token-{video_id}",
            **kwargs,
        )
        session.add(appearance)
        session.flush()
        return appearance.id


@contextmanager
def mock_feed(replacement):
    """Swap the module-level feed fetch, which is not a service-container member."""
    original = steps.youtube_feed.fetch_feed
    steps.youtube_feed.fetch_feed = replacement
    try:
        yield
    finally:
        steps.youtube_feed.fetch_feed = original


def reload(appearance_id: int) -> Appearance:
    with session_scope() as session:
        appearance = session.get(Appearance, appearance_id)
        session.expunge(appearance)
        return appearance


class TestPickingWork:
    def test_a_due_row_is_advanced(self, pilot, fake_services):
        appearance_id = add_appearance("aaaaaaaaaaa")
        set_services(fakes.services(youtube=FakeYouTubeConnector([content_item("aaaaaaaaaaa")])))

        assert worker.run_due_steps(NOW) == 1
        assert reload(appearance_id).status == AppearanceStatus.ENRICHED

    def test_a_row_still_waiting_is_left_alone(self, pilot, fake_services):
        appearance_id = add_appearance("aaaaaaaaaaa", next_attempt_at=NOW + timedelta(hours=1))
        set_services(fakes.services(youtube=FakeYouTubeConnector([content_item("aaaaaaaaaaa")])))

        assert worker.run_due_steps(NOW) == 0
        assert reload(appearance_id).status == AppearanceStatus.DETECTED

    def test_a_terminal_row_is_never_picked_up_again(self, pilot, fake_services):
        add_appearance("bbbbbbbbbbb", status=AppearanceStatus.SKIPPED_SHORT)
        set_services(fakes.services(youtube=FakeYouTubeConnector([])))

        assert worker.run_due_steps(NOW) == 0


class TestTemporaryFailure:
    def test_the_attempt_is_counted_and_a_retry_scheduled(self, pilot, fake_services):
        appearance_id = add_appearance("aaaaaaaaaaa")
        set_services(fakes.services(youtube=FakeYouTubeConnector(fail_with=TemporaryError("boom"))))

        worker.run_due_steps(NOW)

        appearance = reload(appearance_id)
        assert appearance.status == AppearanceStatus.DETECTED
        assert appearance.attempts == 1
        assert appearance.next_attempt_at == retry_at(1, NOW)

    def test_the_bookkeeping_survives_the_steps_rollback(self, pilot, fake_services):
        # The step's transaction is rolled back by the failure; if the counter
        # were written in it, the row would retry forever and never give up.
        appearance_id = add_appearance("aaaaaaaaaaa")
        set_services(fakes.services(youtube=FakeYouTubeConnector(fail_with=TemporaryError("boom"))))

        worker.run_due_steps(NOW)

        assert reload(appearance_id).attempts == 1

    def test_the_error_is_recorded_for_the_operator(self, pilot, fake_services):
        appearance_id = add_appearance("aaaaaaaaaaa")
        set_services(
            fakes.services(youtube=FakeYouTubeConnector(fail_with=TemporaryError("no route")))
        )

        worker.run_due_steps(NOW)

        assert "no route" in reload(appearance_id).last_error

    def test_a_row_recovers_when_the_world_does(self, pilot, fake_services):
        appearance_id = add_appearance("aaaaaaaaaaa")
        connector = FlakyConnector(failures=2, items=[content_item("aaaaaaaaaaa")])
        set_services(fakes.services(youtube=connector))

        worker.run_due_steps(NOW)
        worker.run_due_steps(NOW + timedelta(minutes=5))
        worker.run_due_steps(NOW + timedelta(minutes=20))

        appearance = reload(appearance_id)
        assert appearance.status == AppearanceStatus.ENRICHED
        # A successful step clears the slate, so the next failure starts over.
        assert appearance.attempts == 0
        assert appearance.next_attempt_at is None

    def test_the_row_is_given_up_on_after_the_last_attempt(self, pilot, fake_services):
        appearance_id = add_appearance("aaaaaaaaaaa", attempts=MAX_ATTEMPTS - 1)
        set_services(fakes.services(youtube=FakeYouTubeConnector(fail_with=TemporaryError("boom"))))

        worker.run_due_steps(NOW)

        appearance = reload(appearance_id)
        assert appearance.status == AppearanceStatus.FAILED
        assert appearance.next_attempt_at is None

    def test_and_the_creator_hears_about_it(self, pilot, fake_services):
        # The notice text — "wir haben es mehrfach versucht" — is written for
        # exactly this path, so this is the path that must not stay silent.
        mailer = FakeEmailClient()
        add_appearance("aaaaaaaaaaa", attempts=MAX_ATTEMPTS - 1)
        set_services(
            fakes.services(
                youtube=FakeYouTubeConnector(fail_with=TemporaryError("boom")), email=mailer
            )
        )

        worker.run_due_steps(NOW)

        assert len(mailer.sent) == 1
        assert "nicht verarbeitet" in mailer.last.subject

    def test_a_retry_that_still_has_room_tells_nobody(self, pilot, fake_services):
        # Only the end of the road is worth writing about.
        mailer = FakeEmailClient()
        add_appearance("aaaaaaaaaaa")
        set_services(
            fakes.services(
                youtube=FakeYouTubeConnector(fail_with=TemporaryError("boom")), email=mailer
            )
        )

        worker.run_due_steps(NOW)

        assert mailer.sent == []


class TestIsolationBetweenRows:
    def test_one_bad_row_does_not_undo_another_rows_progress(self, pilot, fake_services):
        good = add_appearance("aaaaaaaaaaa")
        bad = add_appearance("zzzzzzzzzzz")

        class SelectivelyBroken(FakeYouTubeConnector):
            def item_details(self, external_ids):
                if "zzzzzzzzzzz" in external_ids:
                    raise TemporaryError("this one only")
                return super().item_details(external_ids)

        set_services(fakes.services(youtube=SelectivelyBroken([content_item("aaaaaaaaaaa")])))

        worker.run_due_steps(NOW)

        assert reload(good).status == AppearanceStatus.ENRICHED
        assert reload(bad).attempts == 1


class TestPermanentFailure:
    """A step can fail in a way no amount of waiting will fix.

    A revoked API key, a model that will not fill the schema, an address the
    provider refuses: `YouTubeError`, `LLMError` and `EmailError` are all plain
    exceptions. If one of those only propagated, the row would be due again on
    the very next tick, forever, and — because due rows are worked in id order —
    every appearance behind it would starve.
    """

    def test_the_row_is_given_up_on_rather_than_retried_forever(self, pilot, fake_services):
        appearance_id = add_appearance("aaaaaaaaaaa")
        set_services(
            fakes.services(youtube=FakeYouTubeConnector(fail_with=YouTubeError("bad key")))
        )

        worker.run_due_steps(NOW)

        appearance = reload(appearance_id)
        assert appearance.status == AppearanceStatus.FAILED
        assert "bad key" in appearance.last_error

    def test_it_does_not_take_the_rest_of_the_tick_with_it(self, pilot, fake_services):
        doomed = add_appearance("aaaaaaaaaaa")
        later = add_appearance("zzzzzzzzzzz")

        class BrokenForOne(FakeYouTubeConnector):
            def item_details(self, external_ids):
                if "aaaaaaaaaaa" in external_ids:
                    raise YouTubeError("bad key")
                return super().item_details(external_ids)

        set_services(fakes.services(youtube=BrokenForOne([content_item("zzzzzzzzzzz")])))

        worker.run_due_steps(NOW)

        assert reload(doomed).status == AppearanceStatus.FAILED
        # The row with the higher id must still have been worked.
        assert reload(later).status == AppearanceStatus.ENRICHED

    def test_the_creator_is_told(self, pilot, fake_services):
        mailer = FakeEmailClient()
        add_appearance("aaaaaaaaaaa")
        set_services(
            fakes.services(
                youtube=FakeYouTubeConnector(fail_with=YouTubeError("bad key")), email=mailer
            )
        )

        worker.run_due_steps(NOW)

        assert len(mailer.sent) == 1
        assert "nicht verarbeitet" in mailer.last.subject


class TestPollFailure:
    def test_an_unreachable_feed_does_not_abort_the_tick(self, pilot, fake_services):
        # Otherwise a bad half-hour at YouTube stops enrich, transcribe and
        # summarize for every row, and the six-hourly poll turns into a
        # once-a-minute hammering of the endpoint that is already refusing.
        appearance_id = add_appearance("aaaaaaaaaaa")
        set_services(fakes.services(youtube=FakeYouTubeConnector([content_item("aaaaaaaaaaa")])))

        def explode(channel_id, client=None):
            raise YouTubeTemporaryError("youtube is unwell")

        with mock_feed(explode):
            worker.run_tick(NOW, get_settings())

        assert reload(appearance_id).status == AppearanceStatus.ENRICHED

    def test_and_the_poll_interval_is_still_honoured(self, pilot, fake_services):
        set_services(fakes.services())

        def explode(channel_id, client=None):
            raise YouTubeTemporaryError("youtube is unwell")

        with mock_feed(explode):
            worker.run_tick(NOW, get_settings())

        with session_scope() as session:
            run = session.get(JobRun, steps.POLL_FEEDS)
            assert run is not None, "a failed poll must still count as having run"
            assert run.last_run_at == NOW
