"""Turning filtered comments into a :class:`~app.analysis.schemas.Sentiment`."""

from __future__ import annotations

from app.analysis.comments import as_prompt_lines
from app.analysis.llm import Completion, LLMGateway
from app.analysis.prompts import load_prompt
from app.analysis.schemas import Sentiment
from app.config import Settings
from app.sources.base import Comment

PURPOSE = "sentiment"


def analyse_sentiment(
    gateway: LLMGateway, comments: list[Comment], *, title: str, settings: Settings
) -> Completion:
    """Describe how the community reacted.

    Parameters
    ----------
    comments
        Already filtered. Raw comments would produce a summary of the spam.
    """
    return gateway.complete_json(
        model=settings.llm.model_sentiment,
        system=load_prompt("sentiment", settings.llm.sentiment_prompt_version),
        user=f"Title: {title}\n\nComments:\n{as_prompt_lines(comments)}",
        schema=Sentiment,
        max_tokens=settings.llm.max_output_tokens,
    )
