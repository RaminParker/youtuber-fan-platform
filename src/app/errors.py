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


class NeedsOperator(Exception):
    """A rejected credential or an exhausted plan: only a person can fix it.

    Not a :class:`TemporaryError`: retrying would burn the ladder and, after
    ten attempts, give a video up for *our* misconfiguration — and tell its
    creator so. The worker parks the row without counting an attempt and logs
    ``operator.action_needed`` at ERROR, with this message, every time.

    The message names the service, what went wrong (with the provider's own
    words) and what to check, so the log line alone is enough to fix it.
    """

    def __init__(self, service: str, problem: str, fix: str) -> None:
        super().__init__(f"{service}: {problem} — {fix}")
        self.service = service
        self.problem = problem
        self.fix = fix
