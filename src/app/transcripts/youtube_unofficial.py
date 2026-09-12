"""Captions through the unofficial library: the fallback, never the foundation.

It works without any grant, which is what lets the pilot see real summaries
before the OAuth verification is through. It is also a grey zone — YouTube's
terms forbid automated access — so the official provider goes first and this one
catches what is left.

Two operational facts decide most of the code below. Datacentre addresses are
widely blocked, so production needs residential proxies. And the library is not
thread-safe, keeps no timeout of its own and mutates whatever session it is
handed, so it gets a fresh instance and a fresh session per call.
"""

from __future__ import annotations

import re

import requests
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    AgeRestricted,
    IpBlocked,
    NoTranscriptFound,
    PoTokenRequired,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeRequestFailed,
)
from youtube_transcript_api.proxies import WebshareProxyConfig

from app.db.models import Source
from app.sources.base import ContentItem
from app.transcripts.base import (
    Segment,
    Transcript,
    TranscriptTemporaryError,
    TranscriptUnavailable,
)

ORIGIN = "youtube_unofficial"

TIMEOUT_SECONDS = 30
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")

#: Blocked address, rate limit, upstream failure — all worth another try.
_TEMPORARY = (RequestBlocked, IpBlocked, YouTubeRequestFailed)
#: This video will not yield a transcript however often we ask.
_PERMANENT = (
    NoTranscriptFound,
    TranscriptsDisabled,
    AgeRestricted,
    PoTokenRequired,
    VideoUnavailable,
)


class _TimeoutSession(requests.Session):
    """A session with a timeout, because the library sets none.

    Injected by subclassing rather than by mounting an adapter: the proxy
    configuration installs its own adapter and would replace anything mounted.
    """

    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", TIMEOUT_SECONDS)
        return super().request(*args, **kwargs)


class UnofficialCaptions:
    """Reads whatever captions YouTube serves to an ordinary client."""

    origin = ORIGIN

    def __init__(self, proxy_username: str = "", proxy_password: str = "") -> None:
        self._proxy_username = proxy_username
        self._proxy_password = proxy_password

    def fetch(self, source: Source, item: ContentItem, languages: list[str]) -> Transcript:
        """Return the video's captions.

        Raises
        ------
        TranscriptUnavailable
            No captions, disabled, age-restricted, or behind a proof-of-origin
            token the library cannot produce.
        TranscriptTemporaryError
            The address was blocked or the request failed. Worth retrying.
        """
        if not VIDEO_ID.match(item.external_id):
            raise TranscriptUnavailable("unavailable")

        try:
            fetched = self._client().fetch(item.external_id, languages=languages)
        except _TEMPORARY as error:
            raise TranscriptTemporaryError(f"{type(error).__name__}") from error
        except _PERMANENT as error:
            raise TranscriptUnavailable(type(error).__name__) from error

        return Transcript(
            origin=ORIGIN,
            language=fetched.language_code,
            is_generated=fetched.is_generated,
            segments=[Segment(start=s.start, duration=s.duration, text=s.text) for s in fetched],
        )

    def _client(self) -> YouTubeTranscriptApi:
        """Build a fresh client per call: the library is not thread-safe."""
        proxy = (
            WebshareProxyConfig(
                proxy_username=self._proxy_username, proxy_password=self._proxy_password
            )
            if self._proxy_username
            else None
        )
        return YouTubeTranscriptApi(proxy_config=proxy, http_client=_TimeoutSession())
