"""Loading the versioned prompt files.

Prompts are product, not code: they live in Markdown files whose name carries
the version, and the version that produced an analysis is stored with it. That
is what makes "did the new prompt make this better or worse" a question with an
answer.
"""

from __future__ import annotations

import functools
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@functools.lru_cache(maxsize=8)
def load_prompt(name: str, version: str) -> str:
    """Read one prompt file.

    Parameters
    ----------
    name
        ``summary`` or ``sentiment``.
    version
        As configured, e.g. ``v1``.
    """
    return (PROMPT_DIR / f"{name}_{version}.md").read_text(encoding="utf-8")
