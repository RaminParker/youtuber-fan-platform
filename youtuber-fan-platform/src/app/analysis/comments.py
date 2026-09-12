"""Choosing which comments the model gets to see.

A pure function, and deliberately so: it is the cheapest quality lever in the
product. Feeding the model three hundred raw comments produces a summary of the
spam; feeding it the ones that carry an argument produces a picture of the
conversation.
"""

from __future__ import annotations

import re
import unicodedata

from app.config import CommentSettings
from app.sources.base import Comment

_URL = re.compile(r"(https?://|www\.|\b\w+\.(com|de|net|org|io|ly)\b)", re.IGNORECASE)
_NOT_WORDS = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalise(text: str) -> str:
    """Reduce a comment to what makes it the same comment as another one.

    Copy-paste spam varies punctuation, emoji and capitalisation, so those all
    have to go before two comments can be compared.
    """
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )
    return _SPACES.sub(" ", _NOT_WORDS.sub(" ", stripped.casefold())).strip()


def filter_comments(
    comments: list[Comment], settings: CommentSettings, channel_id: str | None = None
) -> list[Comment]:
    """Keep the comments worth analysing, in the order they arrived.

    The order is YouTube's own relevance ranking, which already weighs likes and
    replies — so the filter only removes, never reorders.

    Parameters
    ----------
    comments
        Whatever the connector returned.
    settings
        The thresholds from ``config/settings.toml``.
    channel_id
        The creator's own channel. Their replies are part of the conversation
        but not part of the community's reaction to it.
    """
    kept: list[Comment] = []
    seen: set[str] = set()

    for comment in comments:
        if len(comment.text.split()) < settings.min_words:
            continue
        if settings.drop_with_links and _URL.search(comment.text):
            continue
        if settings.drop_channel_owner and channel_id and comment.author_channel_id == channel_id:
            continue

        fingerprint = normalise(comment.text)
        if not fingerprint or fingerprint in seen:
            continue

        seen.add(fingerprint)
        kept.append(comment)
        if len(kept) >= settings.max_count:
            break

    return kept


def as_prompt_lines(comments: list[Comment]) -> str:
    """Render the survivors for the prompt: likes and text, nothing else.

    No author, no id, no timestamp — the model does not need them and we do not
    want them anywhere near a stored analysis.
    """
    return "\n".join(f"[{comment.like_count}] {comment.text}" for comment in comments)
