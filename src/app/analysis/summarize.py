"""Turning a transcript into a :class:`~app.analysis.schemas.Summary`.

One call, up to a configured transcript length. Above it the item is skipped and
the creator told, which is honest and costs nothing.

``# ponytail: single-call summarisation; add map-reduce chunking when a real
video actually exceeds the ceiling.``
"""

from __future__ import annotations

from app.analysis.llm import Completion, LLMGateway
from app.analysis.prompts import load_prompt
from app.analysis.schemas import Summary
from app.config import Settings
from app.jinja import as_clock
from app.transcripts.base import Segment

PURPOSE = "summary"


class TranscriptTooLong(Exception):
    """The transcript exceeds what one call can be asked to handle."""


def as_marked_lines(segments: list[Segment]) -> str:
    """Render the transcript as ``[mm:ss] text`` lines.

    The markers are the only timestamps the model is allowed to use, and they
    become the jump links into the video. Giving it raw text instead would mean
    either no links or invented ones.
    """
    return "\n".join(f"[{as_clock(segment.start)}] {segment.text}" for segment in segments)


def summarise(
    gateway: LLMGateway,
    segments: list[Segment],
    *,
    title: str,
    channel: str,
    settings: Settings,
) -> Completion:
    """Produce the summary of one item.

    Raises
    ------
    TranscriptTooLong
        Above ``content.max_transcript_chars``. The caller skips the item and
        tells the creator; summarising half a video would be worse than not
        summarising it.
    """
    transcript = as_marked_lines(segments)
    if len(transcript) > settings.content.max_transcript_chars:
        raise TranscriptTooLong(f"{len(transcript)} characters")

    return gateway.complete_json(
        model=settings.llm.model_summary,
        system=load_prompt("summary", settings.llm.summary_prompt_version),
        user=f"Title: {title}\nChannel: {channel}\n\nTranscript:\n{transcript}",
        schema=Summary,
        max_tokens=settings.llm.max_output_tokens,
    )
