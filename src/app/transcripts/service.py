"""The provider chain: try them in order, take the first transcript.

The order is not arbitrary. The official provider is the legally clean one and
goes first whenever the creator has connected YouTube; the unofficial one
catches everything else, including the weeks before Google's verification is
through.
"""

from __future__ import annotations

from app import log
from app.db.models import Source
from app.sources.base import ContentItem
from app.transcripts.base import (
    Transcript,
    TranscriptProvider,
    TranscriptTemporaryError,
    TranscriptUnavailable,
)

logger = log.get_logger(__name__)


def fetch_transcript(
    source: Source,
    item: ContentItem,
    providers: list[TranscriptProvider],
    languages: list[str],
    declined: set[str] | None = None,
) -> Transcript:
    """Return the first transcript any provider can produce.

    Parameters
    ----------
    source
        The channel. The official provider reads and may update its grant.
    item
        The video to transcribe.
    providers
        Tried in order. Pass only the ones that are worth asking — the caller
        decides whether the expensive official one is offered at all.
    languages
        Preference order for caption tracks.
    declined
        Filled with the origin of every provider that said no *permanently*.
        An out-parameter on purpose: the caller needs this even when the chain
        ends by raising, and especially then — a provider that declined should
        not be asked again on the next attempt.

    Raises
    ------
    TranscriptTemporaryError
        Nothing succeeded and at least one provider failed in a way a later
        attempt could survive. Losing a video to one blocked address would be
        the wrong answer, so this outranks "unavailable".
    TranscriptUnavailable
        Every provider said no, permanently. The item is skipped and the creator
        is told why.
    """
    had_temporary_failure = False
    last_reason = "no_provider"

    for provider in providers:
        try:
            transcript = provider.fetch(source, item, languages)
        except TranscriptUnavailable as error:
            last_reason = error.reason
            if declined is not None:
                declined.add(provider.origin)
            logger.info(log.TRANSCRIPT_UNAVAILABLE, provider=provider.origin, reason=error.reason)
            continue
        except TranscriptTemporaryError as error:
            had_temporary_failure = True
            last_reason = str(error)
            logger.warning(log.TRANSCRIPT_UNAVAILABLE, provider=provider.origin, reason=str(error))
            continue

        logger.info(
            log.TRANSCRIPT_FETCHED,
            provider=provider.origin,
            language=transcript.language,
            is_generated=transcript.is_generated,
            segments=len(transcript.segments),
            chars=len(transcript.text),
        )
        return transcript

    if had_temporary_failure:
        raise TranscriptTemporaryError(f"every provider failed, last: {last_reason}")
    raise TranscriptUnavailable(last_reason)
