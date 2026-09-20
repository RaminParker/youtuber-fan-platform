"""The Data API client: duration parsing, chunking, and one place for errors.

Error mapping is tested hard because the whole retry system rests on it: what
this client calls temporary, the worker will retry for about a day; what it
calls permanent ends the row.
"""

import httpx
import pytest

from app.errors import TemporaryError
from app.sources.youtube.data_api import (
    MAX_IDS_PER_CALL,
    CommentsDisabled,
    YouTubeDataApi,
    YouTubeError,
    YouTubeTemporaryError,
    chunked,
    parse_duration,
    uploads_playlist_id,
)


def api_with(handler) -> YouTubeDataApi:
    """A client whose transport is a function, so no socket is ever opened."""
    return YouTubeDataApi("test-key", httpx.Client(transport=httpx.MockTransport(handler)))


def responder(status: int, payload: dict):
    return lambda request: httpx.Response(status, json=payload)


def google_error(reason: str) -> dict:
    return {"error": {"code": 403, "errors": [{"reason": reason}], "message": reason}}


class TestParseDuration:
    @pytest.mark.parametrize(
        ("value", "seconds"),
        [
            ("PT41S", 41),
            ("PT23M41S", 1421),
            ("PT1H4M12S", 3852),
            ("PT2H", 7200),
            ("P1DT2H", 93600),
            ("PT0S", 0),
        ],
    )
    def test_it_reads_the_formats_youtube_actually_sends(self, value, seconds):
        assert parse_duration(value) == seconds

    def test_zero_and_missing_are_different_things(self):
        # PT0S means "still being processed", None means "not reported at all".
        # Neither may be mistaken for "this video is short".
        assert parse_duration("PT0S") == 0
        assert parse_duration(None) is None
        assert parse_duration("") is None

    def test_nonsense_yields_none_rather_than_raising(self):
        assert parse_duration("banana") is None


class TestChunking:
    def test_ids_are_split_at_the_api_limit(self):
        # More than 50 ids in one call is rejected with 400 invalidFilters.
        chunks = chunked([f"id{n}" for n in range(120)])

        assert [len(chunk) for chunk in chunks] == [50, 50, 20]
        assert all(len(chunk) <= MAX_IDS_PER_CALL for chunk in chunks)

    def test_an_empty_list_needs_no_request(self):
        assert chunked([]) == []


class TestUploadsPlaylist:
    def test_uc_becomes_uu(self):
        assert uploads_playlist_id("UCpilot0000000000000000") == "UUpilot0000000000000000"

    def test_an_id_without_the_prefix_is_left_intact(self):
        assert uploads_playlist_id("pilot0000000000000000") == "UUpilot0000000000000000"


class TestErrorMapping:
    @pytest.mark.parametrize("reason", ["rateLimitExceeded", "processingFailure", "backendError"])
    def test_these_reasons_are_worth_retrying(self, reason):
        api = api_with(responder(403, google_error(reason)))

        with pytest.raises(YouTubeTemporaryError):
            api.videos(["aaaaaaaaaaa"])

    @pytest.mark.parametrize("status", [500, 502, 503, 429])
    def test_server_trouble_is_worth_retrying(self, status):
        api = api_with(responder(status, {}))

        with pytest.raises(YouTubeTemporaryError):
            api.videos(["aaaaaaaaaaa"])

    def test_a_network_failure_is_worth_retrying(self):
        def explode(request):
            raise httpx.ConnectError("no route to host")

        with pytest.raises(YouTubeTemporaryError):
            api_with(explode).videos(["aaaaaaaaaaa"])

    def test_every_temporary_error_is_one_the_worker_catches(self):
        # The worker catches exactly TemporaryError; a sibling hierarchy would
        # silently turn a retryable failure into a crash.
        assert issubclass(YouTubeTemporaryError, TemporaryError)

    def test_a_bad_key_is_permanent(self):
        api = api_with(responder(400, google_error("keyInvalid")))

        with pytest.raises(YouTubeError):
            api.videos(["aaaaaaaaaaa"])

    def test_disabled_comments_are_signalled_separately(self):
        # Not an error: a perfectly healthy video may simply have them off.
        api = api_with(responder(403, google_error("commentsDisabled")))

        with pytest.raises(CommentsDisabled):
            api.comment_threads("aaaaaaaaaaa", 10)

    def test_an_unparseable_error_body_still_raises_cleanly(self):
        api = api_with(lambda request: httpx.Response(418, text="<html>teapot</html>"))

        with pytest.raises(YouTubeError):
            api.videos(["aaaaaaaaaaa"])


class TestRequests:
    def test_the_api_key_travels_on_every_call(self):
        seen = {}

        def handler(request):
            seen["key"] = request.url.params.get("key")
            return httpx.Response(200, json={"items": []})

        api_with(handler).videos(["aaaaaaaaaaa"])

        assert seen["key"] == "test-key"

    def test_live_streaming_details_are_requested(self):
        # Without this part a premiere's real start time is invisible, and the
        # delay would be counted from the day it was announced.
        seen = {}

        def handler(request):
            seen["part"] = request.url.params.get("part")
            return httpx.Response(200, json={"items": []})

        api_with(handler).videos(["aaaaaaaaaaa"])

        assert "liveStreamingDetails" in seen["part"]

    def test_comment_threads_are_ordered_by_relevance(self):
        seen = {}

        def handler(request):
            seen.update(request.url.params)
            return httpx.Response(200, json={"items": []})

        api_with(handler).comment_threads("aaaaaaaaaaa", 50)

        assert seen["order"] == "relevance"
        assert seen["textFormat"] == "plainText"

    def test_paging_stops_once_enough_comments_are_collected(self):
        calls = []

        def handler(request):
            calls.append(request.url.params.get("pageToken"))
            return httpx.Response(
                200, json={"items": [{"snippet": {}}] * 100, "nextPageToken": "next"}
            )

        threads = api_with(handler).comment_threads("aaaaaaaaaaa", 250)

        assert len(threads) == 250
        assert len(calls) == 3
