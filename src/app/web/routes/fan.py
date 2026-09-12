"""What a fan sees: the sign-up page and the "online ansehen" page.

Both are branded with the creator's name, logo and accent colour, because the
fan's relationship is with the creator and not with us.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.stored import load_analysis
from app.config import Settings, get_settings
from app.db.models import AnalysisKind, Appearance, AppearanceStatus, Creator, Source
from app.delivery.render import jump_link
from app.web.deps import get_session
from app.web.pages import page

router = APIRouter(tags=["fan"])

#: The online page always shows the full text, whatever variant the creator has
#: chosen for the mail. Manifest §7.6 calls the third variant "Teaser mit
#: Volltext online"; a page mirroring the variant would send a teaser's
#: "weiterlesen" link to another teaser, and the full text would exist nowhere.
PAGE_VARIANT = "detailed"

#: The page is not an archive and must never compete with the video in search.
NO_INDEX = "noindex, nofollow"


def error_page(heading: str, message: str, code: int) -> HTMLResponse:
    """Render a branded error page rather than a bare status line."""
    return page("error", status_code=code, heading=heading, message=message)


@router.get("/k/{slug}", response_class=HTMLResponse)
def handle_signup_page(slug: str, session: Session = Depends(get_session)) -> HTMLResponse:
    """Show the creator's sign-up page: one field, one button, three sentences."""
    creator = session.scalar(select(Creator).where(Creator.slug == slug))
    if creator is None:
        return error_page("Diese Seite gibt es nicht", "Der Link stimmt nicht.", 404)
    return page("signup", creator=creator, accent_color=creator.accent_color)


@router.get("/s/{view_token}", response_class=HTMLResponse)
def handle_summary_page(
    view_token: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Show one summary online.

    The token is the only gate. It is 256 bits of randomness and travels in
    exactly three places — a sent mail, the creator's preview, and the
    confirmation page — so the page needs no further check of the mailing's
    state, and the preview's "online ansehen" link works before the send.

    ``# ponytail: no per-state visibility check; add one if tokens ever leave
    those three channels.``
    """
    found = _appearance_and_creator(session, view_token)
    if found is None:
        return error_page("Diese Seite gibt es nicht", "Der Link stimmt nicht.", 404)
    appearance, creator = found

    if appearance.status == AppearanceStatus.UNAVAILABLE:
        return error_page(
            "Dieses Video gibt es nicht mehr",
            "Der Beitrag wurde gelöscht oder auf privat gestellt. Deshalb ist auch "
            "diese Zusammenfassung nicht mehr abrufbar.",
            status.HTTP_410_GONE,
        )

    summary = load_analysis(session, appearance.id, AnalysisKind.SUMMARY)
    if summary is None:
        return error_page("Noch nicht fertig", "Diese Zusammenfassung entsteht gerade.", 404)

    sentiment = load_analysis(session, appearance.id, AnalysisKind.SENTIMENT)

    return page(
        "summary",
        creator=creator,
        accent_color=creator.accent_color,
        appearance=appearance,
        summary=summary,
        sentiment=sentiment,
        variant=PAGE_VARIANT,
        subscription=None,
        view_url=f"{settings.base_url}/s/{view_token}",
        jump=jump_link(appearance.url),
        headers={"X-Robots-Tag": NO_INDEX},
    )


def _appearance_and_creator(session: Session, view_token: str):
    """Fetch the video and whose it is in one round trip.

    A whole mailing links to this page, so it is hit by every fan who clicks
    "online ansehen", in a burst. Three sequential lookups for two objects is
    the wrong shape for that.
    """
    return session.execute(
        select(Appearance, Creator)
        .join(Source, Source.id == Appearance.source_id)
        .join(Creator, Creator.id == Source.creator_id)
        .where(Appearance.view_token == view_token)
    ).first()
