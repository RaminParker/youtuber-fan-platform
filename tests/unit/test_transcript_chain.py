"""The provider chain decides what counts as "no transcript" and what as "not yet"."""

import pytest

from app.transcripts.base import TranscriptTemporaryError, TranscriptUnavailable
from app.transcripts.service import fetch_transcript
from tests.fakes import FakeTranscriptProvider, content_item, transcript

LANGUAGES = ["de", "en"]


def chain(*providers):
    return fetch_transcript(object(), content_item("aaaaaaaaaaa"), list(providers), LANGUAGES)


class TestOrder:
    def test_the_first_provider_that_answers_wins(self):
        official = FakeTranscriptProvider("youtube_official", transcript("youtube_official"))
        unofficial = FakeTranscriptProvider("youtube_unofficial", transcript())

        result = chain(official, unofficial)

        assert result.origin == "youtube_official"
        assert unofficial.calls == 0

    def test_the_chain_moves_on_when_one_provider_has_nothing(self):
        official = FakeTranscriptProvider(
            "youtube_official", raises=TranscriptUnavailable("no_grant")
        )
        unofficial = FakeTranscriptProvider("youtube_unofficial", transcript())

        result = chain(official, unofficial)

        assert result.origin == "youtube_unofficial"
        assert official.calls == 1

    def test_moving_on_happens_in_the_same_run_not_as_a_retry(self):
        # A missing grant is known immediately; waiting five minutes to ask the
        # other provider would delay every video for no reason.
        official = FakeTranscriptProvider(
            "youtube_official", raises=TranscriptUnavailable("no_grant")
        )
        unofficial = FakeTranscriptProvider("youtube_unofficial", transcript())

        chain(official, unofficial)

        assert (official.calls, unofficial.calls) == (1, 1)


class TestFailure:
    def test_all_providers_permanently_out_means_no_transcript(self):
        with pytest.raises(TranscriptUnavailable) as caught:
            chain(
                FakeTranscriptProvider("a", raises=TranscriptUnavailable("no_grant")),
                FakeTranscriptProvider("b", raises=TranscriptUnavailable("po_token")),
            )

        # The reason shown to the creator is the last one, from the provider
        # that actually could have delivered.
        assert caught.value.reason == "po_token"

    def test_one_temporary_failure_outranks_every_permanent_one(self):
        # Losing a video because a proxy was blocked would be the wrong answer:
        # the retry ladder has about a day, and the minimum delay is two.
        with pytest.raises(TranscriptTemporaryError):
            chain(
                FakeTranscriptProvider("a", raises=TranscriptUnavailable("no_grant")),
                FakeTranscriptProvider("b", raises=TranscriptTemporaryError("IpBlocked")),
            )

    def test_an_empty_chain_is_unavailable_not_a_crash(self):
        with pytest.raises(TranscriptUnavailable):
            chain()
