"""Parsing SubRip, which is what the captions endpoint hands back.

Small enough for the standard library; a dependency would be more code than
this, not less.
"""

from __future__ import annotations

import re

from app.transcripts.base import Segment

# 00:01:02,500 --> 00:01:05,000   (a dot instead of a comma is common in the wild)
_TIMING = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*-->\s*(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)
_TAGS = re.compile(r"</?[a-zA-Z][^>]*>")


def to_seconds(stamp: str) -> float:
    """Convert an SRT timestamp to seconds."""
    hours, minutes, rest = stamp.split(":")
    seconds, _, milliseconds = rest.replace(".", ",").partition(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000


def parse_srt(content: str) -> list[Segment]:
    """Parse an SRT document into segments.

    Blocks without a timing line are skipped rather than raising: a caption file
    is not a contract, and one broken cue must not cost the whole transcript.

    Parameters
    ----------
    content
        The SRT document.
    """
    segments = []
    for block in re.split(r"\n\s*\n", content.replace("\r\n", "\n").strip()):
        segment = _parse_block(block)
        if segment is not None:
            segments.append(segment)
    return segments


def _parse_block(block: str) -> Segment | None:
    """Turn one cue into a :class:`Segment`, or ``None`` if it has no timing."""
    lines = [line for line in block.split("\n") if line.strip()]
    timing_index = next((i for i, line in enumerate(lines) if _TIMING.search(line)), None)
    if timing_index is None:
        return None

    match = _TIMING.search(lines[timing_index])
    start = to_seconds(match.group("start"))
    end = to_seconds(match.group("end"))
    text = " ".join(_TAGS.sub("", line).strip() for line in lines[timing_index + 1 :])
    if not text.strip():
        return None
    return Segment(start=start, duration=max(0.0, end - start), text=text.strip())
