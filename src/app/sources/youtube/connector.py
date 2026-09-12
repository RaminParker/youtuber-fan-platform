"""The YouTube implementation of :class:`~app.sources.base.SourceConnector`.

Everything source-specific ends here: below this line the pipeline only ever
sees ``ContentItem`` and ``Comment``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.sources.base import Comment, ContentItem, SourceProfile
from app.sources.youtube.data_api import (
    CommentsDisabled,
    YouTubeDataApi,
    parse_duration,
    uploads_playlist_id,
    watch_url,
)

_LIVE_STATES = frozenset({"live", "upcoming"})


def to_content_item(resource: dict[str, Any]) -> ContentItem:
    """Map one raw ``videos.list`` resource to a :class:`ContentItem`.

    The publication date deserves its own sentence. For a premiere or a
    broadcast, ``snippet.publishedAt`` is the moment the creator *scheduled* it,
    which can be weeks before anyone could watch. ``actualStartTime`` is the
    moment it went live, and the delay has to count from there — otherwise a
    premiere announced three weeks early would be mailed the day it starts.
    """
    snippet = resource.get("snippet", {})
    status = resource.get("status", {})
    live = resource.get("liveStreamingDetails", {})

    published = live.get("actualStartTime") or snippet.get("publishedAt")
    return ContentItem(
        external_id=resource["id"],
        title=snippet.get("title", ""),
        url=watch_url(resource["id"]),
        published_at=datetime.fromisoformat(published),
        duration_seconds=parse_duration(resource.get("contentDetails", {}).get("duration")),
        is_public=status.get("privacyStatus") == "public",
        is_live_or_upcoming=snippet.get("liveBroadcastContent", "none") in _LIVE_STATES,
        # A video marked as made for kids has its comments disabled by policy,
        # so asking for them would only spend quota on a guaranteed 403.
        comments_disabled=bool(status.get("madeForKids")),
    )


def to_comment(thread: dict[str, Any]) -> Comment:
    """Map one raw ``commentThreads.list`` item to a :class:`Comment`."""
    snippet = thread.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
    author = snippet.get("authorChannelId") or {}
    return Comment(
        text=snippet.get("textDisplay", ""),
        like_count=snippet.get("likeCount", 0),
        author_channel_id=author.get("value"),
    )


class YouTubeConnector:
    """Reads one channel through the public Data API."""

    kind = "youtube"

    def __init__(self, api: YouTubeDataApi) -> None:
        self._api = api

    def source_profile(self, source_external_id: str) -> SourceProfile | None:
        """Return the channel's title and avatar, used as the default branding."""
        channel = self._api.channel(source_external_id)
        if channel is None:
            return None
        snippet = channel.get("snippet", {})
        thumbnail = snippet.get("thumbnails", {}).get("high", {})
        return SourceProfile(
            external_id=channel["id"],
            title=snippet.get("title", ""),
            avatar_url=thumbnail.get("url"),
        )

    def latest_items(self, source_external_id: str, limit: int) -> list[ContentItem]:
        """Return the channel's newest uploads, newest first.

        Goes through the uploads playlist rather than ``search.list``: the same
        one quota unit instead of a hundred, and the playlist is ordered the way
        we want already.
        """
        video_ids = self._api.playlist_video_ids(uploads_playlist_id(source_external_id), limit)
        if not video_ids:
            return []
        return self._ordered(self.item_details(video_ids), video_ids)

    def item_details(self, external_ids: list[str]) -> list[ContentItem]:
        """Return details for the given ids. A missing id means the video is gone."""
        return [to_content_item(resource) for resource in self._api.videos(external_ids)]

    def comments(self, external_id: str, max_count: int) -> list[Comment]:
        """Return public comments, most relevant first.

        Comments being switched off is a normal state of a healthy video, not a
        failure, so it yields an empty list and the mail simply omits the box.
        """
        try:
            threads = self._api.comment_threads(external_id, max_count)
        except CommentsDisabled:
            return []
        return [to_comment(thread) for thread in threads]

    @staticmethod
    def _ordered(items: list[ContentItem], order: list[str]) -> list[ContentItem]:
        """Restore the playlist's order, which ``videos.list`` does not preserve."""
        by_id = {item.external_id: item for item in items}
        return [by_id[video_id] for video_id in order if video_id in by_id]
