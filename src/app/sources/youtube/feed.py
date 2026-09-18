"""The public Atom feed: the cheapest way to notice a new upload.

No API key, no quota, 15 newest entries, cached for about a quarter of an hour.
It carries no duration, no privacy status and no live information, so every
entry still has to be enriched through the Data API before it can be judged.

``# ponytail: a channel publishing more than 15 videos between two polls loses
the overflow; fall back to playlistItems when all 15 ids are already known.``
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from xml.etree import ElementTree

import httpx

from app.sources.youtube.data_api import YouTubeTemporaryError, watch_url

FEED_URL = "https://www.youtube.com/feeds/videos.xml"
FEED_LIMIT = 15
TIMEOUT_SECONDS = 15

_ATOM = "{http://www.w3.org/2005/Atom}"
_YT = "{http://www.youtube.com/xml/schemas/2015}"


@dataclass(frozen=True)
class FeedEntry:
    """One entry of the channel feed."""

    video_id: str
    channel_id: str
    title: str
    published_at: datetime

    @property
    def url(self) -> str:
        """The watch URL, built the one way this project builds it."""
        return watch_url(self.video_id)


def parse_feed(xml: str | bytes) -> list[FeedEntry]:
    """Parse a channel feed into its entries.

    An entry without a video id or a publication date is skipped rather than
    raising: the feed is a convenience, and one malformed entry must not cost us
    the other fourteen.

    Parameters
    ----------
    xml
        The raw feed document.

    Returns
    -------
    list of FeedEntry
        In the order the feed lists them, newest first.
    """
    root = ElementTree.fromstring(xml)
    entries = []
    for element in root.findall(f"{_ATOM}entry"):
        entry = _parse_entry(element)
        if entry is not None:
            entries.append(entry)
    return entries


def _parse_entry(element: ElementTree.Element) -> FeedEntry | None:
    """Turn one ``<entry>`` into a :class:`FeedEntry`, or ``None`` if unusable."""
    video_id = _text(element, f"{_YT}videoId")
    published = _text(element, f"{_ATOM}published")
    if not video_id or not published:
        return None
    return FeedEntry(
        video_id=video_id,
        # The feed-level yt:channelId lacks the UC prefix; the per-entry one has it.
        channel_id=_text(element, f"{_YT}channelId") or "",
        title=_text(element, f"{_ATOM}title") or "",
        published_at=datetime.fromisoformat(published),
    )


def _text(element: ElementTree.Element, path: str) -> str | None:
    """Return the stripped text of a child element, or ``None``."""
    found = element.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def fetch_feed(channel_id: str, client: httpx.Client | None = None) -> list[FeedEntry]:
    """Fetch and parse one channel's feed.

    A plain function rather than a member of the service container: it needs no
    credentials, and its only interesting part — the parsing — is tested from a
    fixture.

    Parameters
    ----------
    client
        Pass one when polling several sources, so that they share a connection.

    Raises
    ------
    YouTubeTemporaryError
        The feed was unreachable, answered with an error, or answered with
        something that is not a feed (a consent or error page).
    """
    owned = client is None
    client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
    try:
        response = client.get(FEED_URL, params={"channel_id": channel_id})
        response.raise_for_status()
        return parse_feed(response.content)
    except httpx.HTTPError as error:
        # Like every other transport here: the caller should not have to know
        # that httpx exists, nor tell a 500 apart from a DNS failure by type.
        raise YouTubeTemporaryError(f"feed for {channel_id}: {error}") from error
    except ElementTree.ParseError as error:
        raise YouTubeTemporaryError(f"feed for {channel_id} is not XML: {error}") from error
    finally:
        if owned:
            client.close()
