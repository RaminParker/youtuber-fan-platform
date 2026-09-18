"""What a fan sees: signing up, confirming, leaving, and the "online ansehen" page.

All of it is branded with the creator's name, logo and accent colour, because
the fan's relationship is with the creator and not with us. The rules behind
signing up and confirming live in ``app.subscriptions``; this module speaks
HTTP.

Two rules shape the handlers, as in the creator area. **A link in a mail never
changes anything by being fetched** — except the confirmation, where a scanner
confirming a sign-up the person asked for is harmless and common. **Nothing
here reveals who is subscribed**: the sign-up form answers the same way, and
as fast, for every address, even when the mail provider is down.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import log, subscriptions
from app.addresses import InvalidAddress, validate
from app.analysis.stored import load_analysis
from app.config import Settings, get_settings
from app.db.models import AnalysisKind, Appearance, AppearanceStatus, Creator, Source, Subscription
from app.delivery.render import jump_link
from app.jinja import render_partial
from app.web.deps import DbSession
from app.web.limits import limiter, signup_limit
from app.web.pages import page

router = APIRouter(tags=["fan"])
logger = log.get_logger(__name__)

INVALID_ADDRESS = "Bitte prüf deine E-Mail-Adresse — an diese können wir nichts schicken."

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


def _creator(session: Session, slug: str) -> Creator | None:
    return session.scalar(select(Creator).where(Creator.slug == slug))


@router.get("/k/{slug}", response_class=HTMLResponse)
def handle_signup_page(slug: str, session: DbSession) -> HTMLResponse:
    """Show the creator's sign-up page: one field, one button, three sentences."""
    creator = _creator(session, slug)
    if creator is None:
        return error_page("Diese Seite gibt es nicht", "Der Link stimmt nicht.", 404)
    return _signup_answer(None, creator)


@router.post("/k/{slug}", response_class=HTMLResponse)
@limiter.limit(signup_limit)
def handle_signup(
    request: Request,
    slug: str,
    session: DbSession,
    background: BackgroundTasks,
    email: str = Form(""),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Record a sign-up; the confirm mail follows once the answer has gone out.

    The answer never depends on what was found: new, pending, confirmed,
    blocked and throttled addresses all read "Schau in dein Postfach". The
    session commits before the answer leaves (``DbSession``), and the mail is
    sent after it (``send_confirm_mail``), so it never carries a token the
    database does not have — and the response time reveals nothing.
    """
    creator = _creator(session, slug)
    if creator is None:
        return error_page("Diese Seite gibt es nicht", "Der Link stimmt nicht.", 404)

    try:
        address = validate(email, check_dns=settings.web.check_address_dns)
    except InvalidAddress as error:
        logger.info(log.SUBSCRIPTION_ADDRESS_REJECTED, reason=str(error))
        return _signup_answer(request, creator, error=INVALID_ADDRESS, email=email)

    subscription = subscriptions.record_sign_up(
        session, creator, address, datetime.now(UTC), settings
    )
    if subscription is not None:
        background.add_task(subscriptions.send_confirm_mail, subscription.id)
    return _signup_answer(request, creator, sent=True)


def _signup_answer(
    request: Request | None,
    creator: Creator,
    *,
    sent: bool = False,
    error: str = "",
    email: str = "",
) -> HTMLResponse:
    """Answer with the whole page, or only the form's place in it when HTMX asked."""
    context = {"creator": creator, "sent": sent, "error": error, "email": email}
    if request is not None and request.headers.get("HX-Request") == "true":
        return HTMLResponse(render_partial("signup_form", **context))
    return page("signup", accent_color=creator.accent_color, **context)


@router.get("/k/{slug}/bestaetigen/{token}", response_class=HTMLResponse)
def handle_confirm(slug: str, token: str, session: DbSession) -> HTMLResponse:
    """Confirm a sign-up. The one GET in the fan area that changes something.

    Idempotent, and the token is kept: a scanner fetching the link first and
    the person clicking it second both see the "Dabei!" page.
    """
    now = datetime.now(UTC)
    found = session.execute(
        select(Subscription, Creator)
        .join(Creator, Creator.id == Subscription.creator_id)
        .where(Subscription.confirm_token == token, Creator.slug == slug)
    ).first()
    if found is None or not subscriptions.confirmable(found.Subscription, now):
        creator = _creator(session, slug)
        return page(
            "action_confirm",
            status_code=status.HTTP_410_GONE,
            heading="Dieser Link gilt nicht mehr",
            body="Trag dich einfach noch einmal ein, dann schicken wir dir einen neuen.",
            action=f"/k/{slug}",
            label="Neu eintragen",
            method="get",
            accent_color=creator.accent_color if creator else None,
        )
    subscription, creator = found

    subscriptions.confirm(subscription, now)
    return page(
        "confirmed",
        creator=creator,
        accent_color=creator.accent_color,
        newest_view_token=subscriptions.newest_received_summary(session, creator),
    )


@router.get("/abmelden/{token}", response_class=HTMLResponse)
def handle_unsubscribe_page(token: str, session: DbSession) -> HTMLResponse:
    """Show one button. Fetching the link changes nothing."""
    creator = subscriptions.creator_for_unsubscribe(session, token)
    return page(
        "action_confirm",
        heading="Abmelden",
        body=f"Ein Klick, und du bekommst von {_channel(creator)} keine Zusammenfassungen mehr.",
        action=f"/abmelden/{token}",
        label="Abmelden",
        accent_color=creator.accent_color if creator else None,
    )


@router.post("/abmelden/{token}", response_class=HTMLResponse)
def handle_unsubscribe(token: str, session: DbSession) -> HTMLResponse:
    """Unsubscribe from this one creator. Also the RFC 8058 one-click endpoint.

    Always 200: a mail client posting one-click has nothing to do with an
    error, and the token is the only thing this could reveal anything about.
    """
    creator = subscriptions.unsubscribe(session, token, datetime.now(UTC))
    return page(
        "error",
        heading="Du bist abgemeldet",
        message=f"Von {_channel(creator)} kommen keine Zusammenfassungen mehr. "
        "Du kannst dich jederzeit wieder eintragen.",
        accent_color=creator.accent_color if creator else None,
    )


def _channel(creator: Creator | None) -> str:
    """Name the channel: a fan following several must see which one they leave."""
    return creator.name if creator else "diesem Kanal"


@router.get("/s/{view_token}", response_class=HTMLResponse)
def handle_summary_page(
    view_token: str,
    session: DbSession,
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
