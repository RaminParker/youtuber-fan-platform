"""The creator area: signing in by e-mail, and connecting YouTube.

Two rules shape almost every handler here.

**A link in a mail never changes anything by being fetched.** Corporate and
webmail scanners follow links before a human sees them; a magic link that signed
someone in on GET would be consumed by a spam filter. So every state-changing
link lands on a page with one button, and the change happens on POST.

**Nothing here reveals who exists.** The sign-in form answers the same way for a
known and an unknown address.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import log
from app.config import Settings, get_settings
from app.db.models import Creator, Source
from app.delivery.render import render_magic_link_mail
from app.services import get_services
from app.sources.youtube.oauth import GrantRevoked, authorization_url, encrypt_token
from app.tokens import new_token
from app.web.deps import SESSION_KEY, current_creator, get_session
from app.web.limits import limiter, magic_link_limit
from app.web.pages import page

router = APIRouter(prefix="/creator", tags=["creator"])
logger = log.get_logger(__name__)

OAUTH_STATE_KEY = "oauth_state"
OAUTH_CALLBACK_PATH = "/creator/youtube/callback"

#: Shown whatever the address was, so the form cannot be used to find out who
#: is a customer.
SIGN_IN_ANSWER = "Wenn es ein Konto zu dieser Adresse gibt, ist der Anmeldelink unterwegs."


def hash_token(token: str) -> str:
    """Hash a magic-link token for storage.

    Stored hashed because a leaked database backup would otherwise be a set of
    working login links.
    """
    return hashlib.sha256(token.encode()).hexdigest()


@router.get("/login", response_class=HTMLResponse)
def handle_login_form() -> HTMLResponse:
    """Show the sign-in form."""
    return page("creator_login")


@router.post("/login", response_class=HTMLResponse)
@limiter.limit(magic_link_limit)
def handle_login_request(
    request: Request,
    email: str = Form(...),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Send a sign-in link, if the address belongs to a creator."""
    creator = session.scalar(select(Creator).where(Creator.contact_email == email.strip().lower()))
    if creator is not None and _needs_a_new_link(creator):
        try:
            _send_magic_link(creator, settings)
        except Exception:
            # A 500 here and a 200 for an unknown address is an existence
            # oracle. The creator can simply ask again; the form must not
            # answer differently depending on who asked.
            logger.exception("creator.magic_link_failed", creator_id=creator.id)
    return page("creator_login", sent=True, message=SIGN_IN_ANSWER)


def _needs_a_new_link(creator: Creator) -> bool:
    """Whether a working link is not already sitting in the creator's inbox.

    One valid link at a time. Without this the only brake is the per-IP limit,
    and a request arriving through a proxy that trusts every forwarded address
    can choose its own IP — which would turn a login form into a way to flood
    somebody's mailbox. A second link would buy nothing anyway: the first one
    still works.
    """
    expires_at = creator.magic_link_expires_at
    return expires_at is None or expires_at <= datetime.now(UTC)


def _send_magic_link(creator: Creator, settings: Settings) -> None:
    """Issue a fresh single-use token and mail it."""
    token = new_token()
    creator.magic_link_token_hash = hash_token(token)
    creator.magic_link_expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.email.magic_link_minutes
    )
    link = f"{settings.base_url}/creator/login/{token}"
    get_services().email.send(render_magic_link_mail(creator, link, settings))
    logger.info("creator.magic_link_sent", creator_id=creator.id)


@router.get("/login/{token}", response_class=HTMLResponse)
def handle_login_confirm_page(token: str) -> HTMLResponse:
    """Show the one-button page the mail's link leads to.

    Deliberately does not consume the token: a link scanner that fetched this
    page would otherwise burn the creator's only way in.
    """
    return page(
        "action_confirm",
        heading="Anmelden",
        body="Klick auf den Knopf, um dich anzumelden.",
        action=f"/creator/login/{token}",
        label="Anmelden",
    )


@router.post("/login/{token}")
def handle_login(
    token: str,
    request: Request,
    session: Session = Depends(get_session),
) -> Response:
    """Consume the token and start the session."""
    creator = _creator_for_token(session, token)
    if creator is None:
        return page(
            "action_confirm",
            heading="Der Link gilt nicht mehr",
            body="Fordere auf der Anmeldeseite einen neuen an.",
            action="/creator/login",
            label="Neuen Link anfordern",
            method="get",
        )

    creator.magic_link_token_hash = None
    creator.magic_link_expires_at = None
    request.session[SESSION_KEY] = creator.id
    logger.info("creator.signed_in", creator_id=creator.id)
    return RedirectResponse("/creator/einstellungen", status_code=303)


def _creator_for_token(session: Session, token: str) -> Creator | None:
    """Return the creator this token signs in, if it is still valid."""
    creator = session.scalar(
        select(Creator).where(Creator.magic_link_token_hash == hash_token(token))
    )
    if creator is None or creator.magic_link_expires_at is None:
        return None
    if creator.magic_link_expires_at < datetime.now(UTC):
        return None
    return creator


@router.post("/abmelden")
def handle_sign_out(request: Request) -> Response:
    """End the session."""
    request.session.clear()
    return RedirectResponse("/creator/login", status_code=303)


@router.get("/youtube/verbinden")
def handle_youtube_connect(
    request: Request,
    creator: Creator = Depends(current_creator),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Send the creator to Google to grant access to their captions."""
    state = new_token()
    request.session[OAUTH_STATE_KEY] = state
    return RedirectResponse(
        authorization_url(
            settings.secrets.google_oauth_client_id,
            f"{settings.base_url}{OAUTH_CALLBACK_PATH}",
            state,
        ),
        status_code=303,
    )


@router.get("/youtube/callback", response_class=HTMLResponse)
def handle_youtube_callback(
    request: Request,
    state: str = "",
    code: str = "",
    session: Session = Depends(get_session),
    creator: Creator = Depends(current_creator),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Store the grant, once it is clear which channel it is for."""
    expected = request.session.pop(OAUTH_STATE_KEY, None)
    if not state or not expected or not secrets.compare_digest(state, expected):
        return _connect_failed("Die Anfrage kam nicht von hier. Bitte versuch es noch einmal.")
    if not code:
        return _connect_failed("Google hat die Freigabe nicht bestätigt.")

    source = session.scalar(select(Source).where(Source.creator_id == creator.id))
    if source is None:
        return _connect_failed("Für dein Konto ist noch kein Kanal hinterlegt.")

    try:
        connected = get_services().youtube_connection.complete(
            code, f"{settings.base_url}{OAUTH_CALLBACK_PATH}"
        )
    except GrantRevoked:
        return _connect_failed("Die Freigabe wurde nicht erteilt.")

    if connected.channel_id != source.external_id:
        # Connecting somebody else's channel would mean reading the wrong
        # captions for as long as the grant lasts.
        return _connect_failed(
            "Der freigegebene Kanal ist nicht der Kanal, der hier hinterlegt ist."
        )

    source.oauth_refresh_token_enc = encrypt_token(
        connected.refresh_token, settings.secrets.token_encryption_keys
    )
    source.oauth_granted_at = datetime.now(UTC)
    source.oauth_needs_reconsent = False
    logger.info("oauth.connected", creator_id=creator.id, source_id=source.id)

    return page(
        "action_confirm",
        heading="YouTube ist verbunden",
        body="Ab jetzt holen wir die Untertitel offiziell über deinen Kanal.",
        action="/creator/einstellungen",
        label="Weiter zu den Einstellungen",
        method="get",
    )


def _connect_failed(reason: str) -> HTMLResponse:
    """Render the "that did not work" page with a way to try again."""
    return page(
        "action_confirm",
        heading="Verbindung nicht hergestellt",
        body=reason,
        action="/creator/youtube/verbinden",
        label="Noch einmal versuchen",
        method="get",
    )
