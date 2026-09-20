"""How the worker is told what kind of trouble it is in.

Three answers, and the row's fate follows from which one it gets:

- :class:`TemporaryError` — try again later. Every layer subclasses it: the
  YouTube client, the OAuth client, the transcript providers, the mail client.
  It costs an attempt, and ten of them end the row.
- :class:`NeedsOperator` — a key or a plan; only a person can fix it. It costs
  no attempt and never ends a row on its own.
- :class:`CostCapExceeded` — the budget for today; only the clock fixes it.

Anything else is a bug or a permanent condition its step has already mapped to
a terminal status.
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
