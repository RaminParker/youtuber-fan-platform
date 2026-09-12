"""What every source connector returns, whatever it is connected to.

The interface is one of the two abstractions the manifest asks for from day one.
Phase 2 adds a podcast connector as a second implementation and nothing below
this layer changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ContentItem:
    """One publication: a video today, an episode later.

    Attributes
    ----------
    duration_seconds
        ``None`` while the platform is still processing the recording. That is
        not the same as "short", and the pipeline must not confuse the two.
    published_at
        When the item became publicly available. For a premiere or a stream
        that is the moment it went live, not the moment it was scheduled.
    """

    external_id: str
    title: str
    url: str
    published_at: datetime
    duration_seconds: int | None
    is_public: bool
    is_live_or_upcoming: bool
    comments_disabled: bool


@dataclass(frozen=True)
class Comment:
    """One public comment, reduced to what the sentiment analysis needs."""

    text: str
    like_count: int
    author_channel_id: str | None


@dataclass(frozen=True)
class SourceProfile:
    """How a source presents itself: used to onboard it and to brand its pages."""

    external_id: str
    title: str
    avatar_url: str | None


class SourceConnector(Protocol):
    """The contract every source fulfils."""

    kind: str

    def source_profile(self, source_external_id: str) -> SourceProfile | None:
        """Return the source's own name and picture, or ``None`` if unknown."""
        ...

    def latest_items(self, source_external_id: str, limit: int) -> list[ContentItem]:
        """Return the newest items of one source, newest first."""
        ...

    def item_details(self, external_ids: list[str]) -> list[ContentItem]:
        """Return details for the given ids. An id that is absent was deleted."""
        ...

    def comments(self, external_id: str, max_count: int) -> list[Comment]:
        """Return public comments. Empty for sources that have none."""
        ...
