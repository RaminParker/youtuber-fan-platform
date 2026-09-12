"""The one error the worker treats as "try again later".

Every layer subclasses it — the YouTube client, the OAuth client, the transcript
providers, the mail client's quota error. The worker catches exactly this type,
counts an attempt and schedules a retry; anything else is a bug or a permanent
condition that its step has already mapped to a terminal status.
"""

from __future__ import annotations


class TemporaryError(Exception):
    """A failure that a later attempt could plausibly survive."""


class CostCapExceeded(Exception):
    """The creator's daily LLM budget is used up.

    Deliberately not a :class:`TemporaryError`. Retrying would burn attempts on
    a condition that only the clock can change, and after ten of them the row
    would be given up on for having been *cheap*. The worker parks it until the
    cap resets instead.
    """
