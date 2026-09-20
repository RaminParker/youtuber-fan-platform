"""What the model must return. These are the contract, not a suggestion.

Every field is filled on every call, whatever mail variant the creator has
chosen: the variants are templates over one analysis, so switching from compact
to detailed must never require summarising the video again.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    """No field beyond the declared ones.

    The provider refuses a strict output schema unless every object says
    ``additionalProperties: false``; ``extra="forbid"`` is what makes pydantic
    write it. It also means an answer with unexpected fields fails validation
    (and gets the one retry) instead of being stored half-understood.
    """

    model_config = ConfigDict(extra="forbid")


class KeyPoint(Strict):
    """One thing that was said, with the place in the video where it was said."""

    text: str = Field(description="One sentence, in the language of the video.")
    timestamp_seconds: int | None = Field(
        default=None, description="Seconds from the start, taken from a marker in the transcript."
    )


class Section(Strict):
    """A stretch of the talk that belongs together."""

    title: str
    key_points: list[KeyPoint]


class Summary(Strict):
    """The full analysis of one item. Every mail variant renders from this."""

    language: str = Field(description="ISO code of the language the video is in.")
    headline: str = Field(description="A sober line, never a question, never clickbait.")
    core_message: str = Field(description="Two sentences: what this was about.")
    key_points: list[KeyPoint] = Field(description="Three to five, always filled.")
    sections: list[Section] = Field(description="Two to four, always filled.")
    quote: str = Field(description="One strong sentence, verbatim from the transcript.")
    quote_timestamp_seconds: int | None = None


class Sentiment(Strict):
    """How the community reacted, as far as the comments show it."""

    overall: str = Field(description="Two or three sentences on the prevailing mood.")
    agreed: list[str] = Field(description="Points that landed well.")
    disagreed: list[str] = Field(description="Points that met resistance.")
    questions: list[str] = Field(description="What the community is asking.")
    comment_count_used: int = 0
