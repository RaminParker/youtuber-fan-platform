"""What a transcript is, and the two ways fetching one can fail.

This is the first of the two abstractions the manifest asks for from day one.
It has two implementations already — official captions and the unofficial
library — which is precisely why it earns its Protocol.

The two error types matter more than they look. ``TranscriptUnavailable`` means
"this will never work for this video": the chain moves on to the next provider
and, if none succeeds, the item is skipped and the creator told.
``TranscriptTemporaryError`` means "not right now": the worker retries for about
a day, comfortably inside the 48-hour minimum delay.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.errors import TemporaryError


@dataclass(frozen=True)
class Segment:
    """One caption cue: when it starts, how long it lasts, what is said."""

    start: float
    duration: float
    text: str


@dataclass(frozen=True)
class Transcript:
    """A full transcript, with the provenance the law cares about."""

    origin: str
    language: str
    is_generated: bool
    segments: list[Segment]

    @property
    def text(self) -> str:
        """The plain text. Derived on read, never stored a second time."""
        return " ".join(segment.text for segment in self.segments if segment.text)

    def as_json(self) -> list[dict[str, float | str]]:
        """Return the segments in the shape the database column holds."""
        return [{"start": s.start, "duration": s.duration, "text": s.text} for s in self.segments]


class TranscriptUnavailable(Exception):
    """There is no transcript to be had for this item, now or later.

    Parameters
    ----------
    reason
        One of ``no_captions``, ``disabled``, ``age_restricted``, ``po_token``,
        ``forbidden``, ``no_grant``, ``unavailable``. Recorded on the row and
        shown to the creator, so it has to stay readable.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class TranscriptTemporaryError(TemporaryError):
    """Blocked address, rate limit, network. Worth trying again later."""


class TranscriptProvider(Protocol):
    """One way of getting a transcript."""

    origin: str

    def fetch(self, source, item, languages: list[str]) -> Transcript:
        """Return a transcript, or raise one of the two errors above."""
        ...
