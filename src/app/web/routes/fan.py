"""What a fan sees: signing up, confirming, leaving, and the "online ansehen" page.

All of it is branded with the creator's name, logo and accent colour, because
the fan's relationship is with the creator and not with us.

Two rules shape the handlers, as in the creator area. **A link in a mail never
changes anything by being fetched** — except the confirmation, where a scanner
confirming a sign-up the person asked for is harmless and common. **Nothing
here reveals who is subscribed**: the sign-up form answers the same way for
every address, even when the mail provider is down.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import log
from app.analysis.stored import load_analysis
from app.config import Settings, get_settings
from app.db.models import (
    AnalysisKind,
    Appearance,
    AppearanceStatus,
    BlockedReason,
    Creator,
    Mailing,
    MailingStatus,
    Source,
    Subscriber,
    Subscription,
    SubscriptionStatus,
)
from app.delivery.render import jump_link, render_confirm_mail
from app.jinja import get_jinja
from app.services import get_services
from app.tokens import new_token
from app.web.deps import get_session
from app.web.limits import limiter, signup_limit
from app.web.pages import page

router = APIRouter(tags=["fan"])
logger = log.get_logger(__name__)

#: Deliberately loose: the confirm mail is the real test of an address. This
#: only stops what is obviously not one before it costs a send.
ADDRESS = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_ADDRESS_LENGTH = 320
INVALID_ADDRESS = "Bitte gib eine gültige E-Mail-Adresse ein."

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
    return _signup_page(creator)


def _signup_page(creator: Creator, *, sent: bool = False, error: str = "") -> HTMLResponse:
    return page(
        "signup", creator=creator, accent_color=creator.accent_color, sent=sent, error=error
    )


@router.post("/k/{slug}", response_class=HTMLResponse)
@limiter.limit(signup_limit)
def handle_signup(
    request: Request,
    slug: str,
    email: str = Form(""),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    """Record a sign-up and send the confirm mail, if one is due.

    The answer never depends on what was found: new, pending, confirmed,
    blocked and throttled addresses all read "Schau in dein Postfach".
    """
    creator = session.scalar(select(Creator).where(Creator.slug == slug))
    if creator is None:
        return error_page("Diese Seite gibt es nicht", "Der Link stimmt nicht.", 404)

    address = email.strip().lower()
    if len(address) > MAX_ADDRESS_LENGTH or not ADDRESS.match(address):
        return _signup_answer(request, creator, error=INVALID_ADDRESS)

    subscription = _record_sign_up(session, creator, address, datetime.now(UTC), settings)
    if subscription is not None:
        # Committed before sending: the mail must never carry a token the
        # database does not have.
        session.commit()
        _send_confirm_mail(session, creator, subscription, address, settings)
    return _signup_answer(request, creator, sent=True)


def _signup_answer(request: Request, creator: Creator, **state) -> HTMLResponse:
    """Answer with the whole page, or only the form's place in it when HTMX asked."""
    if request.headers.get("HX-Request") != "true":
        return _signup_page(creator, **state)
    context = {"creator": creator, "sent": False, "error": ""} | state
    return HTMLResponse(get_jinja().get_template("partials/signup_form.html").render(**context))


def _record_sign_up(
    session: Session, creator: Creator, address: str, now: datetime, settings: Settings
) -> Subscription | None:
    """Apply the sign-up rules and return the subscription to mail, if any.

    ``None`` means: send nothing, answer as usual. That is the case for an
    address that complained about us, and for one that got a confirm mail
    within ``web.confirm_resend_minutes`` — the per-IP limit alone would let
    one sender flood a stranger's inbox, and the complaints would land on the
    sending domain every creator shares.
    """
    subscriber = _upsert(session, Subscriber, {"email": address}, ["email"])
    if subscriber.blocked_reason == BlockedReason.COMPLAINT:
        return None

    subscription = _upsert(
        session,
        Subscription,
        {
            "subscriber_id": subscriber.id,
            "creator_id": creator.id,
            "status": SubscriptionStatus.PENDING,
            "unsubscribe_token": new_token(),
        },
        ["subscriber_id", "creator_id"],
    )
    window = timedelta(minutes=settings.web.confirm_resend_minutes)
    if subscription.confirm_sent_at is not None and subscription.confirm_sent_at + window > now:
        return None

    # A confirmed fan is never demoted by the public form: they only get the
    # mail again, and its link lands on the "Dabei!" page.
    if subscription.status != SubscriptionStatus.CONFIRMED:
        subscription.status = SubscriptionStatus.PENDING
        subscription.confirm_token = new_token()
        subscription.confirm_expires_at = now + timedelta(days=settings.email.confirm_token_days)
        subscription.unsubscribed_at = None
        logger.info(log.SUBSCRIPTION_CREATED, subscription_id=subscription.id)
    subscription.confirm_sent_at = now
    return subscription


def _upsert(session: Session, model, values: dict, unique: list[str]):
    """Insert a row unless it exists, then return it locked.

    ``ON CONFLICT`` rather than select-then-insert: two simultaneous sign-ups
    of one address would otherwise end in a unique violation, a 500, and an
    answer that differs from everyone else's. The row lock makes the second
    one wait and then see the first one's ``confirm_sent_at``.
    """
    session.execute(insert(model).values(**values).on_conflict_do_nothing(index_elements=unique))
    key = [getattr(model, column) == values[column] for column in unique]
    return session.scalar(select(model).where(*key).with_for_update(of=model))


def _send_confirm_mail(
    session: Session, creator: Creator, subscription: Subscription, address: str, settings: Settings
) -> None:
    """Send the confirm mail; on failure, leave the address free to try again."""
    link = f"{settings.base_url}/k/{creator.slug}/bestaetigen/{subscription.confirm_token}"
    try:
        get_services().email.send(render_confirm_mail(creator, address, link, settings))
    except Exception:
        # Same answer as always: a failure must not tell a known address from
        # an unknown one. And no throttle for a mail that never left.
        logger.exception("subscription.confirm_failed", subscription_id=subscription.id)
        subscription.confirm_sent_at = None


@router.get("/k/{slug}/bestaetigen/{token}", response_class=HTMLResponse)
def handle_confirm(slug: str, token: str, session: Session = Depends(get_session)) -> HTMLResponse:
    """Confirm a sign-up. The one GET in the fan area that changes something.

    Idempotent, and the token is kept: a scanner fetching the link first and
    the person clicking it second both see the "Dabei!" page.
    """
    found = session.execute(
        select(Subscription, Creator)
        .join(Creator, Creator.id == Subscription.creator_id)
        .where(Subscription.confirm_token == token, Creator.slug == slug)
    ).first()
    now = datetime.now(UTC)
    if found is None or not _confirmable(found.Subscription, now):
        return page(
            "action_confirm",
            status_code=status.HTTP_410_GONE,
            heading="Dieser Link gilt nicht mehr",
            body="Trag dich einfach noch einmal ein, dann schicken wir dir einen neuen.",
            action=f"/k/{slug}",
            label="Neu eintragen",
            method="get",
        )
    subscription, creator = found

    if subscription.status == SubscriptionStatus.PENDING:
        subscription.status = SubscriptionStatus.CONFIRMED
        subscription.confirmed_at = now
        # The confirm mail arrived, so the mailbox works again.
        if subscription.subscriber.blocked_reason == BlockedReason.BOUNCE:
            subscription.subscriber.blocked_at = None
            subscription.subscriber.blocked_reason = None
        logger.info(log.SUBSCRIPTION_CONFIRMED, subscription_id=subscription.id)

    return page(
        "confirmed",
        creator=creator,
        accent_color=creator.accent_color,
        newest_view_token=_newest_received_summary(session, creator),
    )


def _confirmable(subscription: Subscription, now: datetime) -> bool:
    """Tell whether the link still confirms: confirmed already, or pending and in time.

    An unsubscribed fan's old link does not count: a fetched link must not
    undo a decision to leave.
    """
    if subscription.status == SubscriptionStatus.CONFIRMED:
        return True
    return (
        subscription.status == SubscriptionStatus.PENDING
        and subscription.confirm_expires_at is not None
        and subscription.confirm_expires_at > now
    )


def _newest_received_summary(session: Session, creator: Creator) -> str | None:
    """Return the view token of the newest summary the list has already received.

    Back catalogue, or a mailing that went out. Never an open, stopped or
    cancelled one: the page must not hand out a summary before the list gets
    it, or after the creator decided it should not go out (manifest §3.1).
    """
    return session.scalar(
        select(Appearance.view_token)
        .join(Source, Source.id == Appearance.source_id)
        .outerjoin(Mailing, Mailing.appearance_id == Appearance.id)
        .where(
            Source.creator_id == creator.id,
            Appearance.status == AppearanceStatus.ANALYZED,
            or_(Appearance.is_backfill, Mailing.status == MailingStatus.SENT),
        )
        .order_by(Appearance.published_at.desc())
        .limit(1)
    )


@router.get("/abmelden/{token}", response_class=HTMLResponse)
def handle_unsubscribe_page(token: str, session: Session = Depends(get_session)) -> HTMLResponse:
    """Show one button. Fetching the link changes nothing."""
    creator = _creator_for_unsubscribe(session, token)
    return page(
        "action_confirm",
        heading="Abmelden",
        body=f"Ein Klick, und du bekommst von {_channel(creator)} keine Zusammenfassungen mehr.",
        action=f"/abmelden/{token}",
        label="Abmelden",
        accent_color=creator.accent_color if creator else None,
    )


@router.post("/abmelden/{token}", response_class=HTMLResponse)
def handle_unsubscribe(token: str, session: Session = Depends(get_session)) -> HTMLResponse:
    """Unsubscribe from this one creator. Also the RFC 8058 one-click endpoint.

    Always 200: a mail client posting one-click has nothing to do with an
    error, and the token is the only thing this could reveal anything about.
    """
    result = session.execute(
        update(Subscription)
        .where(
            Subscription.unsubscribe_token == token,
            Subscription.status != SubscriptionStatus.UNSUBSCRIBED,
        )
        .values(status=SubscriptionStatus.UNSUBSCRIBED, unsubscribed_at=datetime.now(UTC))
        .returning(Subscription.id)
    )
    subscription_id = result.scalar()
    if subscription_id is not None:
        logger.info(log.SUBSCRIPTION_UNSUBSCRIBED, subscription_id=subscription_id)
    creator = _creator_for_unsubscribe(session, token)
    return page(
        "error",
        heading="Du bist abgemeldet",
        message=f"Von {_channel(creator)} kommen keine Zusammenfassungen mehr. "
        "Du kannst dich jederzeit wieder eintragen.",
        accent_color=creator.accent_color if creator else None,
    )


def _creator_for_unsubscribe(session: Session, token: str) -> Creator | None:
    return session.scalar(
        select(Creator)
        .join(Subscription, Subscription.creator_id == Creator.id)
        .where(Subscription.unsubscribe_token == token)
    )


def _channel(creator: Creator | None) -> str:
    """Name the channel: a fan following several must see which one they leave."""
    return creator.name if creator else "diesem Kanal"


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
