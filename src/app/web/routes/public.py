"""The sales page and the pages the law requires."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.web.deps import get_session
from app.web.pages import page

router = APIRouter(tags=["public"])


@router.get("/", response_class=HTMLResponse)
def handle_landing(settings: Settings = Depends(get_settings)) -> HTMLResponse:
    """Show the sales page."""
    return page("landing", support_email=settings.support_email)


@router.get("/impressum", response_class=HTMLResponse)
def handle_imprint() -> HTMLResponse:
    """Show the imprint."""
    return page("legal", heading="Impressum", body=IMPRINT_PLACEHOLDER)


@router.get("/datenschutz", response_class=HTMLResponse)
def handle_privacy() -> HTMLResponse:
    """Show the privacy notice."""
    return page("legal", heading="Datenschutz", body=PRIVACY_PLACEHOLDER)


@router.get("/health", include_in_schema=False)
def handle_health(session: Session = Depends(get_session)) -> dict[str, str]:
    """Report readiness, database included."""
    session.execute(text("SELECT 1"))
    return {"status": "ok"}


# TODO: replace with the text the owner and their lawyer provide. Both pages
# must name the YouTube API Services and link Google's privacy policy.
IMPRINT_PLACEHOLDER = (
    "Dieser Text fehlt noch. Vor dem Start trägt der Betreiber hier Anbieterkennzeichnung, "
    "Kontaktdaten und Verantwortlichen ein."
)
PRIVACY_PLACEHOLDER = (
    "Dieser Text fehlt noch. Vor dem Start trägt der Betreiber hier die Datenschutzerklärung "
    "ein, einschließlich des Hinweises auf die YouTube API Services und die "
    "Datenschutzerklärung von Google."
)
