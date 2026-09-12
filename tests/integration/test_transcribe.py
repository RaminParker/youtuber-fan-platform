"""The transcribe step: persisting provenance, skipping cleanly, telling the creator."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models import (
    Appearance,
    AppearanceStatus,
    Creator,
    NoticeKind,
    Source,
    SourceKind,
    Transcript,
    TranscriptOrigin,
)
from app.jobs import steps
from app.services import set_services
from app.transcripts.base import TranscriptTemporaryError, TranscriptUnavailable
from tests import fakes
from tests.fakes import FakeEmailClient, FakeTranscriptProvider, transcript

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
ONBOARDED = datetime(2026, 9, 1, tzinfo=UTC)


@pytest.fixture
def appearance(session):
    creator = Creator(slug="pilot", name="Pilotkanal", contact_email="pilot@example.org")
    session.add(creator)
    session.flush()
    source = Source(
        creator_id=creator.id,
        kind=SourceKind.YOUTUBE,
        external_id="UCpilot0000000000000000",
        created_at=ONBOARDED,
    )
    session.add(source)
    session.flush()
    appearance = Appearance(
        source_id=source.id,
        external_id="aaaaaaaaaaa",
        title="Warum Verwaltung so langsam ist",
        url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
        published_at=NOW - timedelta(days=1),
        duration_seconds=1421,
        status=AppearanceStatus.ENRICHED,
        view_token="view-token",
    )
    session.add(appearance)
    session.flush()
    return appearance


def run(session, appearance, providers, email=None):
    mailer = email or FakeEmailClient()
    set_services(fakes.services(transcripts=providers, email=mailer))
    steps.transcribe(session, appearance.id, NOW)
    session.flush()
    session.refresh(appearance)
    return mailer


class TestSuccess:
    def test_the_transcript_is_stored_with_its_origin(self, session, appearance, fake_services):
        # Provenance is stored because it is legally relevant: official captions
        # and the unofficial library are not the same thing in a dispute.
        run(session, appearance, [FakeTranscriptProvider("youtube_unofficial", transcript())])

        stored = session.scalar(select(Transcript))
        assert stored.origin == TranscriptOrigin.YOUTUBE_UNOFFICIAL
        assert stored.language == "de"
        assert len(stored.segments) == 2
        assert appearance.status == AppearanceStatus.TRANSCRIBED

    def test_the_plain_text_is_derived_not_stored_twice(self, session, appearance, fake_services):
        run(session, appearance, [FakeTranscriptProvider("youtube_unofficial", transcript())])

        stored = session.scalar(select(Transcript))
        assert "text" not in stored.segments[0] or stored.segments[0]["text"]
        assert not hasattr(stored, "plain_text")

    def test_a_successful_step_clears_the_retry_bookkeeping(
        self, session, appearance, fake_services
    ):
        appearance.attempts = 3
        appearance.last_error = "IpBlocked"

        run(session, appearance, [FakeTranscriptProvider("youtube_unofficial", transcript())])

        assert appearance.attempts == 0
        assert appearance.last_error is None

    def test_a_row_in_the_wrong_status_is_left_alone(self, session, appearance, fake_services):
        appearance.status = AppearanceStatus.TRANSCRIBED
        session.flush()

        run(session, appearance, [FakeTranscriptProvider("youtube_unofficial", transcript())])

        assert session.scalar(select(Transcript)) is None


class TestNoTranscript:
    def test_the_item_is_skipped_and_the_creator_is_told(self, session, appearance, fake_services):
        mailer = run(
            session,
            appearance,
            [
                FakeTranscriptProvider(
                    "youtube_unofficial", raises=TranscriptUnavailable("po_token")
                )
            ],
        )

        assert appearance.status == AppearanceStatus.SKIPPED_NO_TRANSCRIPT
        assert appearance.skip_reason == "po_token"
        assert len(mailer.sent) == 1
        assert mailer.last.to == "pilot@example.org"

    def test_the_notice_names_the_video(self, session, appearance, fake_services):
        mailer = run(
            session,
            appearance,
            [
                FakeTranscriptProvider(
                    "youtube_unofficial", raises=TranscriptUnavailable("no_captions")
                )
            ],
        )

        assert "Warum Verwaltung so langsam ist" in mailer.last.text

    def test_the_notice_is_keyed_so_retries_cannot_repeat_it(
        self, session, appearance, fake_services
    ):
        mailer = run(
            session,
            appearance,
            [
                FakeTranscriptProvider(
                    "youtube_unofficial", raises=TranscriptUnavailable("no_captions")
                )
            ],
        )

        assert mailer.last.idempotency_key == f"notice/{NoticeKind.NO_TRANSCRIPT}/{appearance.id}"

    def test_an_undeliverable_notice_does_not_undo_the_skip(
        self, session, appearance, fake_services
    ):
        # The step did its job; a broken mailbox must not turn that into a crash.
        mailer = FakeEmailClient(fail_with=RuntimeError("mail server on fire"))

        run(
            session,
            appearance,
            [
                FakeTranscriptProvider(
                    "youtube_unofficial", raises=TranscriptUnavailable("no_captions")
                )
            ],
            email=mailer,
        )

        assert appearance.status == AppearanceStatus.SKIPPED_NO_TRANSCRIPT


class TestTemporaryFailure:
    def test_it_is_raised_so_the_worker_can_retry(self, session, appearance, fake_services):
        set_services(
            fakes.services(
                transcripts=[
                    FakeTranscriptProvider(
                        "youtube_unofficial", raises=TranscriptTemporaryError("IpBlocked")
                    )
                ]
            )
        )

        with pytest.raises(TranscriptTemporaryError):
            steps.transcribe(session, appearance.id, NOW)

    def test_nothing_is_written(self, session, appearance, fake_services):
        set_services(
            fakes.services(
                transcripts=[
                    FakeTranscriptProvider(
                        "youtube_unofficial", raises=TranscriptTemporaryError("IpBlocked")
                    )
                ]
            )
        )

        with pytest.raises(TranscriptTemporaryError):
            steps.transcribe(session, appearance.id, NOW)

        assert appearance.status == AppearanceStatus.ENRICHED


class TestTheExpensiveProviderIsOfferedOnce:
    def test_the_first_attempt_may_ask_the_official_provider(
        self, session, appearance, fake_services
    ):
        source = session.get(Source, appearance.source_id)
        source.oauth_refresh_token_enc = "encrypted"
        official = FakeTranscriptProvider("youtube_official", transcript("youtube_official"))

        run(
            session,
            appearance,
            [official, FakeTranscriptProvider("youtube_unofficial", transcript())],
        )

        assert official.calls == 1

    def test_a_row_it_already_declined_skips_it(self, session, appearance, fake_services):
        # 250 quota units per attempt, for a provider that already said no.
        source = session.get(Source, appearance.source_id)
        source.oauth_refresh_token_enc = "encrypted"
        appearance.official_captions_declined = True
        official = FakeTranscriptProvider("youtube_official", transcript("youtube_official"))

        run(
            session,
            appearance,
            [official, FakeTranscriptProvider("youtube_unofficial", transcript())],
        )

        assert official.calls == 0

    def test_a_mere_retry_does_not_disable_it(self, session, appearance, fake_services):
        # The retry counter belongs to every step. Reading it as "the official
        # provider has declined" meant an IP block at the *unofficial* provider
        # disabled the official one — including for a creator who connects
        # YouTube precisely because the first attempt failed.
        source = session.get(Source, appearance.source_id)
        source.oauth_refresh_token_enc = "encrypted"
        appearance.attempts = 3
        official = FakeTranscriptProvider("youtube_official", transcript("youtube_official"))

        run(
            session,
            appearance,
            [official, FakeTranscriptProvider("youtube_unofficial", transcript())],
        )

        assert official.calls == 1

    def test_without_a_grant_it_is_never_asked_at_all(self, session, appearance, fake_services):
        official = FakeTranscriptProvider("youtube_official", transcript("youtube_official"))

        run(
            session,
            appearance,
            [official, FakeTranscriptProvider("youtube_unofficial", transcript())],
        )

        assert official.calls == 0


class TestRevokedGrant:
    def test_the_creator_is_asked_to_reconnect_once(self, session, appearance, fake_services):
        source = session.get(Source, appearance.source_id)
        source.oauth_refresh_token_enc = "encrypted"

        class RevokingProvider(FakeTranscriptProvider):
            def fetch(self, source, item, languages):
                source.oauth_needs_reconsent = True
                raise TranscriptUnavailable("no_grant")

        mailer = run(
            session,
            appearance,
            [
                RevokingProvider("youtube_official"),
                FakeTranscriptProvider("youtube_unofficial", transcript()),
            ],
        )

        kinds = [mail.tags.get("kind") for mail in mailer.sent]
        assert kinds == ["notice"]
        assert "YouTube" in mailer.last.subject
        # The unofficial provider saved the video, so it is not skipped.
        assert appearance.status == AppearanceStatus.TRANSCRIBED

    def test_a_temporary_failure_sends_no_notice_at_all(self, session, appearance, fake_services):
        # The step's transaction is about to be rolled back, taking the flag —
        # and any rotated refresh token — with it. A notice sent anyway would
        # report a state that was never saved, and the next video would report
        # it again.
        source = session.get(Source, appearance.source_id)
        source.oauth_refresh_token_enc = "encrypted"
        mailer = FakeEmailClient()

        class RevokingThenBlocked(FakeTranscriptProvider):
            def fetch(self, source, item, languages):
                source.oauth_needs_reconsent = True
                raise TranscriptUnavailable("no_grant")

        set_services(
            fakes.services(
                transcripts=[
                    RevokingThenBlocked("youtube_official"),
                    FakeTranscriptProvider(
                        "youtube_unofficial", raises=TranscriptTemporaryError("IpBlocked")
                    ),
                ],
                email=mailer,
            )
        )

        with pytest.raises(TranscriptTemporaryError):
            steps.transcribe(session, appearance.id, NOW)

        assert mailer.sent == []

    def test_an_already_flagged_source_is_not_reported_again(
        self, session, appearance, fake_services
    ):
        # Otherwise every video would write to the creator about the same grant.
        source = session.get(Source, appearance.source_id)
        source.oauth_needs_reconsent = True

        mailer = run(
            session, appearance, [FakeTranscriptProvider("youtube_unofficial", transcript())]
        )

        assert mailer.sent == []
