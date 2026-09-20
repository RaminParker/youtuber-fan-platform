"""The creator's emergency brake: the stop and postpone links from the preview.

A link scanner follows links before a human sees them, so GET only shows a
page with one button and POST acts. The token is the credential — 256 bits,
rotated with every new schedule, useless once the send has begun.

Every answer tells the truth about the mail. "Gestoppt" appears only when this
request stopped it; a mail already on its way, already stopped, or cancelled
says exactly that.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse

from app.config import Settings, get_settings
from app.db.models import MAILING_STOPPABLE, Appearance, Creator, Mailing, MailingStatus
from app.delivery import mailing as mailings
from app.jinja import long_datetime
from app.jobs.schedule import postponed_send_at
from app.web.deps import DbSession
from app.web.pages import error_page, page

router = APIRouter(tags=["mailing"])

UNDO_HINT = "Das lässt sich nicht rückgängig machen."


def _when(moment: datetime, settings: Settings) -> str:
    return long_datetime(moment, settings.product.timezone)


@router.get("/m/{token}/stoppen", response_class=HTMLResponse)
def handle_stop_page(
    token: str, session: DbSession, settings: Settings = Depends(get_settings)
) -> HTMLResponse:
    """Ask once, naming the mail and its send time, whether to stop it."""
    found = mailings.find_by_token(session, token)
    if found is None or found.Mailing.status not in MAILING_STOPPABLE:
        return _truth(found)
    mailing, appearance, creator = found
    return _stop_offer(token, mailing, appearance, creator, settings, heading="Diese Mail stoppen?")


@router.post("/m/{token}/stoppen", response_class=HTMLResponse)
def handle_stop(token: str, session: DbSession) -> HTMLResponse:
    """Stop the mail — or say truthfully why that is no longer possible."""
    found = mailings.find_by_token(session, token)
    if found is None or not mailings.stop(session, token, datetime.now(UTC)):
        return _truth(mailings.find_by_token(session, token))
    _, appearance, creator = found
    return error_page(
        "Gestoppt",
        f"„{appearance.title}“ geht nicht an deine Abonnenten.",
        status.HTTP_200_OK,
        creator=creator,
        role="status",
    )


@router.get("/m/{token}/verschieben", response_class=HTMLResponse)
def handle_postpone_page(
    token: str, session: DbSession, settings: Settings = Depends(get_settings)
) -> HTMLResponse:
    """Ask once, naming the new time. Past the cap only stopping is left."""
    found = mailings.find_by_token(session, token)
    if found is None or found.Mailing.status not in MAILING_STOPPABLE:
        return _truth(found)
    mailing, appearance, creator = found
    new_send_at = postponed_send_at(mailing.send_at, appearance.published_at, settings.schedule)
    if new_send_at is None:
        return _past_the_cap(token, mailing, appearance, creator, settings)
    return page(
        "action_confirm",
        heading="Diese Mail verschieben?",
        body=(
            f"„{appearance.title}“ geht dann am {_when(new_send_at, settings)} raus statt am "
            f"{_when(mailing.send_at, settings)}. Eine Stunde vorher bekommst du eine neue Vorschau."
        ),
        action=f"/m/{token}/verschieben",
        label=f"Verschieben auf {_when(new_send_at, settings)}",
        creator=creator,
    )


@router.post("/m/{token}/verschieben", response_class=HTMLResponse)
def handle_postpone(
    token: str, session: DbSession, settings: Settings = Depends(get_settings)
) -> HTMLResponse:
    """Move the send and start the schedule over; the links of this preview die."""
    found = mailings.find_by_token(session, token)
    if found is None or found.Mailing.status not in MAILING_STOPPABLE:
        return _truth(found)
    mailing, appearance, creator = found
    new_send_at = postponed_send_at(mailing.send_at, appearance.published_at, settings.schedule)
    if new_send_at is None:
        return _past_the_cap(token, mailing, appearance, creator, settings)
    if not mailings.postpone(session, token, mailing.send_at, new_send_at):
        return _truth(mailings.find_by_token(session, token), raced=True)
    return error_page(
        "Verschoben",
        f"„{appearance.title}“ geht jetzt am {_when(new_send_at, settings)} raus. Eine Stunde "
        "vorher bekommst du eine neue Vorschau; die Links aus dieser Mail gelten nicht mehr.",
        status.HTTP_200_OK,
        creator=creator,
        role="status",
    )


def _stop_offer(
    token: str,
    mailing: Mailing,
    appearance: Appearance,
    creator: Creator,
    settings: Settings,
    *,
    heading: str,
    reason: str = "",
) -> HTMLResponse:
    """Render the one-button page that stops a mail."""
    return page(
        "action_confirm",
        heading=heading,
        body=(
            f"{reason}„{appearance.title}“ soll am {_when(mailing.send_at, settings)} an deine "
            f"Abonnenten gehen. Gestoppt geht sie gar nicht raus. {UNDO_HINT}"
        ),
        action=f"/m/{token}/stoppen",
        label="Mail stoppen",
        creator=creator,
    )


def _past_the_cap(token, mailing, appearance, creator, settings) -> HTMLResponse:
    """Postponing further would send the summary too long after the video."""
    return _stop_offer(
        token,
        mailing,
        appearance,
        creator,
        settings,
        heading="Verschieben geht nicht mehr",
        reason="Später käme die Zusammenfassung zu lange nach dem Video. ",
    )


#: What to say about a mail the links can no longer change, by its state.
TRUTH = {
    MailingStatus.SENDING: (
        "Die Mail ist schon unterwegs",
        "Sie wird gerade an deine Abonnenten verschickt. Stoppen oder verschieben geht nicht mehr.",
    ),
    MailingStatus.SENT: (
        "Die Mail ist schon verschickt",
        "Sie ist bei deinen Abonnenten angekommen. Stoppen oder verschieben geht nicht mehr.",
    ),
    MailingStatus.STOPPED: (
        "Die Mail war bereits gestoppt",
        "Sie geht nicht an deine Abonnenten. Du musst nichts weiter tun.",
    ),
    MailingStatus.CANCELLED: (
        "Diese Mail geht nicht raus",
        "Das Video ist nicht mehr öffentlich, deshalb verschicken wir die Zusammenfassung nicht.",
    ),
    MailingStatus.FAILED: (
        "Diese Mail ist nicht rausgegangen",
        "Beim Versand ging etwas schief. Wir kümmern uns darum und melden uns bei dir.",
    ),
}


def _truth(found, *, raced: bool = False) -> HTMLResponse:
    """Answer a link that can no longer act, saying why — never "gestoppt"."""
    if found is None:
        return error_page(
            "Dieser Link gilt nicht mehr",
            "Zu dieser Mail gibt es eine neuere Vorschau. Nimm bitte die Links aus der "
            "neuesten Mail.",
            status.HTTP_410_GONE,
            role="alert",
        )
    mailing, _, creator = found
    if raced or mailing.status in MAILING_STOPPABLE:
        heading, message = (
            "Die Sendezeit hat sich gerade geändert",
            "Öffne den Link bitte noch einmal, dann siehst du den aktuellen Stand.",
        )
    else:
        heading, message = TRUTH[MailingStatus(mailing.status)]
    return error_page(heading, message, status.HTTP_409_CONFLICT, creator=creator, role="alert")
