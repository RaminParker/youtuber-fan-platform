"""A thin client for the YouTube Data API. Transport and error mapping only.

Four read endpoints and, from M2, the two caption endpoints. Written against
``httpx`` rather than ``google-api-python-client``: the official client would
add about ten transitive packages to save nothing on six GETs.

Quota matters more than latency here. The daily allowance is 10,000 units and
resets at midnight Pacific, so every call logs what it spent and the retry
ladder simply waits an exhausted quota out.
"""

from __future__ import annotations

import re
from typing import Any, NoReturn

import httpx

from app import log
from app.errors import TemporaryError

API_BASE = "https://www.googleapis.com/youtube/v3"
WATCH_URL = "https://www.youtube.com/watch?v={video_id}"
TIMEOUT_SECONDS = 30

#: Ids per request. More than 50 is rejected with 400 invalidFilters.
MAX_IDS_PER_CALL = 50
#: The API's own ceiling for a page of comment threads.
MAX_COMMENTS_PER_PAGE = 100

#: What each endpoint costs. Grep `quota.youtube` in the logs for the real bill.
QUOTA_UNITS = {
    "videos.list": 1,
    "channels.list": 1,
    "playlistItems.list": 1,
    "commentThreads.list": 1,
    "captions.list": 50,
    "captions.download": 200,
}

#: Error reasons that a later attempt could survive.
_TEMPORARY_REASONS = frozenset(
    {"quotaExceeded", "rateLimitExceeded", "processingFailure", "backendError", "internalError"}
)

_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)

logger = log.get_logger(__name__)


class YouTubeError(Exception):
    """A permanent failure: the request will not succeed by being repeated."""


class YouTubeTemporaryError(TemporaryError):
    """A failure worth retrying: quota, rate limit, network, 5xx."""


class CommentsDisabled(Exception):
    """The video has no comments to read. A normal state, not a failure."""


class CaptionsNotAvailable(Exception):
    """The owner has no downloadable caption track for this video.

    Carries the reason so the transcript layer can pass it on unchanged.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def watch_url(video_id: str) -> str:
    """Return the canonical watch URL. The one place this shape is written.

    It ends up in `appearances.url`, and `jump_link` appends `&t=…s` to it, so
    a feed-ingested row and an API-ingested row have to agree on it exactly.
    """
    return WATCH_URL.format(video_id=video_id)


def parse_duration(value: str | None) -> int | None:
    """Convert an ISO-8601 duration to seconds.

    Returns ``None`` for a missing or unparseable value, and ``0`` for ``PT0S``
    — which YouTube reports for a livestream recording it is still processing.
    The caller must keep those two apart from "this video is short".

    Parameters
    ----------
    value
        For example ``PT1H2M10S``.
    """
    if not value:
        return None
    match = _DURATION.match(value)
    if match is None:
        return None
    parts = {name: int(number or 0) for name, number in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def chunked(values: list[str], size: int = MAX_IDS_PER_CALL) -> list[list[str]]:
    """Split a list of ids into request-sized pieces."""
    return [values[start : start + size] for start in range(0, len(values), size)]


def uploads_playlist_id(channel_id: str) -> str:
    """Derive the uploads playlist from a channel id.

    The ``UC`` → ``UU`` substitution is undocumented but has held for a decade;
    ``channels.list?part=contentDetails`` is the documented fallback and costs
    the same one unit.
    """
    return "UU" + channel_id.removeprefix("UC")


def _reason(payload: dict[str, Any]) -> str:
    """Pull Google's machine-readable error reason out of a response body."""
    errors = payload.get("error", {}).get("errors") or [{}]
    return errors[0].get("reason", "")


class YouTubeDataApi:
    """One method per endpoint, one place where errors become our error types."""

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS)

    def _get(
        self, endpoint: str, params: dict[str, Any], access_token: str | None = None
    ) -> dict[str, Any]:
        """Perform one call and map every failure mode exactly once.

        Parameters
        ----------
        endpoint
            For example ``videos.list``; the path is its first segment.
        params
            Query parameters. The API key is added here.

        Raises
        ------
        YouTubeTemporaryError
            Network trouble, 5xx, 429, exhausted quota, processing failure.
        CommentsDisabled
            The video does not accept comments.
        YouTubeError
            Anything else the server refused.
        """
        path = endpoint.split(".")[0]
        response = self._request(endpoint, path, params, access_token)
        if response.is_success:
            return response.json()
        self._raise_for(endpoint, response)

    def _request(
        self, endpoint: str, path: str, params: dict[str, Any], access_token: str | None
    ) -> httpx.Response:
        """Perform the call, log what it cost, and turn network trouble into ours."""
        units = QUOTA_UNITS[endpoint]
        headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}
        query = dict(params) if access_token else {**params, "key": self._api_key}
        try:
            response = self._client.get(f"{API_BASE}/{path}", params=query, headers=headers)
        except httpx.HTTPError as error:
            raise YouTubeTemporaryError(f"{endpoint}: {error}") from error

        logger.info(log.QUOTA_YOUTUBE, endpoint=endpoint, units=units, status=response.status_code)
        return response

    def _raise_for(self, endpoint: str, response: httpx.Response) -> NoReturn:
        """Map one failed response to exactly one of our error types."""
        payload = safe_json(response)
        reason = _reason(payload)
        if response.status_code >= 500 or response.status_code == 429:
            raise YouTubeTemporaryError(f"{endpoint}: HTTP {response.status_code}")
        if reason in _TEMPORARY_REASONS:
            raise YouTubeTemporaryError(f"{endpoint}: {reason}")
        if reason in {"commentsDisabled", "videoCommentsDisabled"}:
            raise CommentsDisabled(endpoint)
        raise YouTubeError(
            f"{endpoint}: HTTP {response.status_code} {reason or response.text[:200]}"
        )

    def captions_list(self, video_id: str, access_token: str) -> list[dict[str, Any]]:
        """Return the video's caption tracks. 50 units, owner authorisation only."""
        payload = self._get(
            "captions.list",
            {
                "part": "snippet",
                "videoId": video_id,
                "fields": "items(id,snippet(language,trackKind,name))",
            },
            access_token,
        )
        return payload.get("items", [])

    def captions_download(self, caption_id: str, access_token: str) -> str:
        """Download one caption track as SubRip. 200 units.

        Neither a 403 nor a 404 is ever retried: each attempt costs 200 units,
        and neither answer changes by being asked again.
        """
        response = self._request(
            "captions.download", f"captions/{caption_id}", {"tfmt": "srt"}, access_token
        )
        if response.is_success:
            return response.text
        if response.status_code in (403, 404):
            raise CaptionsNotAvailable(
                "forbidden" if response.status_code == 403 else "no_captions"
            )
        self._raise_for("captions.download", response)
        raise AssertionError("unreachable")

    def videos(self, video_ids: list[str]) -> list[dict[str, Any]]:
        """Return raw video resources. Ids that are absent were deleted.

        ``liveStreamingDetails`` costs no extra unit and is the only way to know
        when a premiere actually went live.
        """
        items: list[dict[str, Any]] = []
        for chunk in chunked(video_ids):
            payload = self._get(
                "videos.list",
                {
                    "part": "snippet,contentDetails,status,liveStreamingDetails",
                    "id": ",".join(chunk),
                    "maxResults": MAX_IDS_PER_CALL,
                    "fields": (
                        "items(id,snippet(title,publishedAt,channelId,liveBroadcastContent),"
                        "contentDetails/duration,status(privacyStatus,madeForKids),"
                        "liveStreamingDetails/actualStartTime)"
                    ),
                },
            )
            items.extend(payload.get("items", []))
        return items

    def channel(self, channel_id: str) -> dict[str, Any] | None:
        """Return one channel resource, or ``None`` if there is no such channel."""
        payload = self._get(
            "channels.list",
            {
                "part": "snippet,contentDetails",
                "id": channel_id,
                "fields": (
                    "items(id,snippet(title,thumbnails/high/url),"
                    "contentDetails/relatedPlaylists/uploads)"
                ),
            },
        )
        items = payload.get("items", [])
        return items[0] if items else None

    def channel_mine(self, access_token: str) -> dict[str, Any] | None:
        """Return the channel the access token belongs to.

        The callback needs this: without it a creator could connect somebody
        else's channel, and we would read the wrong captions forever.
        """
        payload = self._get(
            "channels.list",
            {"part": "snippet", "mine": "true", "fields": "items(id,snippet/title)"},
            access_token,
        )
        items = payload.get("items", [])
        return items[0] if items else None

    def playlist_video_ids(self, playlist_id: str, limit: int) -> list[str]:
        """Return the newest video ids of a playlist, newest first."""
        ids: list[str] = []
        page_token: str | None = None
        while len(ids) < limit:
            payload = self._get(
                "playlistItems.list",
                {
                    "part": "contentDetails",
                    "playlistId": playlist_id,
                    "maxResults": min(MAX_IDS_PER_CALL, limit - len(ids)),
                    "fields": "nextPageToken,items/contentDetails/videoId",
                    **({"pageToken": page_token} if page_token else {}),
                },
            )
            ids.extend(
                item["contentDetails"]["videoId"]
                for item in payload.get("items", [])
                if item.get("contentDetails", {}).get("videoId")
            )
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return ids[:limit]

    def comment_threads(self, video_id: str, max_count: int) -> list[dict[str, Any]]:
        """Return top-level comments, most relevant first.

        With an API key only ``textDisplay`` is readable; ``textOriginal`` is
        reserved for the channel owner. ``authorChannelId`` may be absent.
        """
        comments: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(comments) < max_count:
            payload = self._get(
                "commentThreads.list",
                {
                    "part": "snippet",
                    "videoId": video_id,
                    "order": "relevance",
                    "textFormat": "plainText",
                    "maxResults": min(MAX_COMMENTS_PER_PAGE, max_count - len(comments)),
                    "fields": (
                        "nextPageToken,items/snippet/topLevelComment/snippet"
                        "(textDisplay,likeCount,authorChannelId/value)"
                    ),
                    **({"pageToken": page_token} if page_token else {}),
                },
            )
            comments.extend(payload.get("items", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return comments[:max_count]


def safe_json(response: httpx.Response) -> dict[str, Any]:
    """Return the parsed body, or an empty mapping if it is not JSON."""
    try:
        parsed = response.json()
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
