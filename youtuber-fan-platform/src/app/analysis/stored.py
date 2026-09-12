"""Reading analyses back out of the database, as the models that produced them.

The column holds `model_dump(mode="json")` of a `Summary` or a `Sentiment`, and
the row's own `kind` says which. Validating on the way back in costs nothing and
buys two things: templates read `summary.quote` in a mail and on a page with one
spelling, and a row written by an older prompt version fails here, loudly, with
the field it is missing — instead of exploding mid-render in front of a fan.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.schemas import Sentiment, Summary
from app.db.models import Analysis, AnalysisKind

MODELS: dict[str, type[Summary] | type[Sentiment]] = {
    AnalysisKind.SUMMARY: Summary,
    AnalysisKind.SENTIMENT: Sentiment,
}


def load_analysis(
    session: Session, appearance_id: int, kind: AnalysisKind
) -> Summary | Sentiment | None:
    """Return one stored analysis, or ``None`` if there is none of that kind.

    A missing sentiment is a normal state — comments switched off, or nothing
    surviving the filter — and the templates render the box only when it is
    there.
    """
    row = session.scalar(
        select(Analysis).where(Analysis.appearance_id == appearance_id, Analysis.kind == kind)
    )
    return MODELS[kind].model_validate(row.content) if row else None
