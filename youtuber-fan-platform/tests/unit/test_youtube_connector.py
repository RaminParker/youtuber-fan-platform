"""Mapping raw API resources to the source-independent objects."""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.sources.youtube.connector import YouTubeConnector, to_comment, to_content_item
from app.sources.youtube.data_api import YouTubeDataApi

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
VIDEOS = json.loads((FIXTURES / "videos.json").read_text(encoding="utf-8"))["items"]
COMMENTS = json.loads((FIXTURES / "comments.json").read_text(encoding="utf-8"))["items"]

BY_ID = {resource["id"]: resource for resource in VIDEOS}


def item(video_id: str):
    return to_content_item(BY_ID[video_id])


class TestPublishedAt:
    def test_a_normal_upload_uses_its_publication_date(self):
        assert item("aaaaaaaaaaa").published_at == datetime(2026, 9, 8, 16, 0, 3, tzinfo=UTC)

    def test_a_broadcast_uses_the_time_it_actually_started(self):
        # snippet.publishedAt would be 20 August: the day it was announced.
        # Counting the delay from there would mail it far too early.
        assert item("eeeeeeeeeee").published_at == datetime(2026, 9, 10, 19, 0, tzinfo=UTC)

    def test_every_date_is_timezone_aware(self):
        assert all(to_content_item(r).published_at.tzinfo is not None for r in VIDEOS)


class TestVisibility:
    def test_a_public_video_is_public(self):
        assert item("aaaaaaaaaaa").is_public is True

    def test_a_private_video_is_not(self):
        assert item("fffffffffff").is_public is False

    def test_an_upcoming_premiere_is_marked_as_such(self):
        assert item("ddddddddddd").is_live_or_upcoming is True

    def test_a_finished_broadcast_is_no_longer_upcoming(self):
        assert item("eeeeeeeeeee").is_live_or_upcoming is False


class TestDuration:
    def test_a_long_video_is_measured_in_seconds(self):
        assert item("aaaaaaaaaaa").duration_seconds == 1421

    def test_a_short_is_measured_too(self):
        assert item("bbbbbbbbbbb").duration_seconds == 41

    def test_an_unprocessed_premiere_reports_zero_not_none(self):
        # The pipeline must treat this as "unknown", never as "too short".
        assert item("ddddddddddd").duration_seconds == 0


class TestComments:
    def test_text_and_likes_are_carried_over(self):
        comment = to_comment(COMMENTS[0])

        assert comment.text.startswith("Endlich sagt das mal jemand")
        assert comment.like_count == 412

    def test_the_author_is_kept_so_the_channel_can_be_filtered_out(self):
        assert to_comment(COMMENTS[2]).author_channel_id == "UCpilot0000000000000000"

    def test_a_missing_author_is_none_not_a_crash(self):
        # authorChannelId is genuinely absent on some comments.
        assert to_comment(COMMENTS[3]).author_channel_id is None


class TestConnector:
    @pytest.fixture
    def connector(self):
        def handler(request):
            if "playlistItems" in request.url.path:
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {"contentDetails": {"videoId": vid}}
                            for vid in ["eeeeeeeeeee", "aaaaaaaaaaa", "bbbbbbbbbbb"]
                        ]
                    },
                )
            if "commentThreads" in request.url.path:
                return httpx.Response(200, json={"items": COMMENTS})
            requested = set(request.url.params["id"].split(","))
            return httpx.Response(200, json={"items": [r for r in VIDEOS if r["id"] in requested]})

        transport = httpx.MockTransport(handler)
        return YouTubeConnector(YouTubeDataApi("k", httpx.Client(transport=transport)))

    def test_latest_items_keeps_the_playlist_order(self, connector):
        # videos.list does not preserve the order the ids were asked for.
        items = connector.latest_items("UCpilot0000000000000000", limit=3)

        assert [i.external_id for i in items] == ["eeeeeeeeeee", "aaaaaaaaaaa", "bbbbbbbbbbb"]

    def test_a_deleted_video_is_simply_absent(self, connector):
        # That absence is how the pipeline learns a video is gone.
        items = connector.item_details(["aaaaaaaaaaa", "gonegonegon"])

        assert [i.external_id for i in items] == ["aaaaaaaaaaa"]

    def test_comments_come_back_mapped(self, connector):
        comments = connector.comments("aaaaaaaaaaa", max_count=10)

        assert len(comments) == 4
        assert comments[1].like_count == 97

    def test_disabled_comments_yield_an_empty_list(self):
        def handler(request):
            return httpx.Response(403, json={"error": {"errors": [{"reason": "commentsDisabled"}]}})

        connector = YouTubeConnector(
            YouTubeDataApi("k", httpx.Client(transport=httpx.MockTransport(handler)))
        )

        assert connector.comments("aaaaaaaaaaa", max_count=10) == []
