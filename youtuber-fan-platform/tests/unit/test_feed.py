"""The public feed is the upload trigger; parsing it must not surprise anyone."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.errors import TemporaryError
from app.sources.youtube.data_api import YouTubeTemporaryError
from app.sources.youtube.feed import fetch_feed, parse_feed

FEED = (Path(__file__).resolve().parents[1] / "fixtures" / "feed.xml").read_text(encoding="utf-8")


@pytest.fixture
def entries():
    return parse_feed(FEED)


class TestParsing:
    def test_it_reads_every_usable_entry(self, entries):
        assert [entry.video_id for entry in entries] == [
            "aaaaaaaaaaa",
            "bbbbbbbbbbb",
            "ccccccccccc",
        ]

    def test_an_entry_without_a_video_id_is_skipped_not_fatal(self, entries):
        # One malformed entry must not cost us the other fourteen.
        assert all(entry.video_id for entry in entries)
        assert "Kaputter Eintrag" not in [entry.title for entry in entries]

    def test_the_newest_entry_comes_first(self, entries):
        assert entries == sorted(entries, key=lambda e: e.published_at, reverse=True)

    def test_titles_survive_umlauts(self, entries):
        assert entries[2].title == "Das Interview, über das alle reden"


class TestChannelId:
    def test_the_entry_level_id_is_used_because_it_has_the_uc_prefix(self, entries):
        # The feed-level yt:channelId does not; using it would break every lookup.
        assert all(entry.channel_id.startswith("UC") for entry in entries)


class TestPublishedAt:
    def test_it_is_timezone_aware_utc(self, entries):
        published = entries[0].published_at

        assert published.tzinfo is not None
        assert published == datetime(2026, 9, 8, 16, 0, 3, tzinfo=UTC)

    def test_published_is_read_not_updated(self, entries):
        # <updated> changes when the creator edits the title; <published> does not.
        assert entries[0].published_at.day == 8


class TestRobustness:
    def test_an_empty_feed_yields_nothing(self):
        empty = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'

        assert parse_feed(empty) == []

    def test_bytes_and_text_parse_alike(self, entries):
        assert parse_feed(FEED.encode("utf-8")) == entries


class TestFetching:
    """The feed maps its own failures, like every other transport here."""

    def test_a_network_failure_becomes_a_temporary_error(self):
        def explode(request):
            raise httpx.ConnectError("no route to host")

        with pytest.raises(YouTubeTemporaryError):
            fetch_feed("UCpilot0", httpx.Client(transport=httpx.MockTransport(explode)))

    @pytest.mark.parametrize("status", [404, 500, 503])
    def test_an_error_response_does_too(self, status):
        transport = httpx.MockTransport(lambda request: httpx.Response(status))

        with pytest.raises(YouTubeTemporaryError):
            fetch_feed("UCpilot0", httpx.Client(transport=transport))

    def test_the_caller_never_has_to_know_about_httpx(self):
        # The worker catches exactly TemporaryError; anything else aborts a tick.
        assert issubclass(YouTubeTemporaryError, TemporaryError)

    def test_a_shared_client_is_used_when_one_is_passed(self):
        # Polling several sources should not mean a handshake per channel.
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(200, content=FEED.encode())

        client = httpx.Client(transport=httpx.MockTransport(handler))
        fetch_feed("UCone", client)
        fetch_feed("UCtwo", client)

        assert len(calls) == 2
        assert not client.is_closed
