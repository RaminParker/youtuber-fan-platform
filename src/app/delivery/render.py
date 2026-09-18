"""Composing mails. Every outgoing message is built here and nowhere else.

Keeping composition in one module is what makes the two "fingerprints" the
manifest asks for enforceable: a creator header and a platform footer on every
message, with no path that can quietly skip them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from types import SimpleNamespace

import css_inline

from app.config import Settings
from app.creator_settings import effective_settings
from app.db.models import Creator, NoticeKind
from app.jinja import get_jinja


@dataclass(frozen=True)
class OutgoingEmail:
    """One message, ready to post."""

    from_: str
    to: str
    subject: str
    html: str
    text: str
    reply_to: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    idempotency_key: str | None = None
    tags: dict[str, str] = field(default_factory=dict)


def sender(creator: Creator, settings: Settings) -> str:
    """Build the From line.

    "Creator via Product" is the platform fingerprint the manifest asks for: the
    fan sees whose mail it is and who built it, in one line, before opening it.
    """
    return f"{creator.name} via {settings.product.name} <{settings.sender_address}>"


def reply_to(creator: Creator, settings: Settings) -> str:
    """Return an address that accepts answers.

    Never a no-reply: a fan replying to a summary is the best thing that can
    happen to a creator's list.
    """
    return creator.reply_to_email or settings.support_email


def inline(html: str) -> str:
    """Inline the stylesheet, because mail clients ignore a ``<style>`` block.

    Remote stylesheets stay switched off: a mail must render the same in a year,
    offline, in a client that blocks everything.
    """
    return css_inline.inline(html, inline_style_tags=True, load_remote_stylesheets=False)


def render_pair(template: str, creator: Creator, subject: str, **context) -> tuple[str, str]:
    """Render an HTML template and its plain-text twin.

    The text part is a template of its own rather than stripped-down HTML:
    heuristic stripping produces exactly the kind of mail that looks broken in
    the one client the recipient happens to use. ``subject`` is passed in, not
    written in the template, so the mail's subject line and its HTML title are
    one value.
    """
    jinja = get_jinja()
    full = {"creator": creator, "accent": creator.accent_color, "subject": subject, **context}
    html = inline(jinja.get_template(f"email/{template}.html").render(**full))
    text = jinja.get_template(f"email/{template}.txt").render(**full)
    return html, text


def render_notice_mail(
    creator: Creator,
    kind: NoticeKind,
    settings: Settings,
    *,
    video_title: str = "",
    appearance_id: int | str = "none",
    action_url: str = "",
) -> OutgoingEmail:
    """Build a message telling the creator that something needs their attention.

    The idempotency key ties the notice to what caused it, so a step that
    retries ten times does not write to the creator ten times about one video.
    """
    notice = NOTICES[kind]
    html, text = render_pair(
        "creator_notice",
        creator,
        notice.subject,
        headline=notice.headline,
        explanation=notice.explanation,
        what_now=notice.what_now,
        video_title=video_title,
        action_url=action_url,
        action_label=notice.action_label,
    )
    return OutgoingEmail(
        from_=sender(creator, settings),
        to=creator.contact_email,
        subject=notice.subject,
        html=html,
        text=text,
        reply_to=settings.support_email,
        idempotency_key=f"notice/{kind}/{appearance_id}",
        tags={"kind": "notice"},
    )


def render_magic_link_mail(creator: Creator, link: str, settings: Settings) -> OutgoingEmail:
    """Build the login mail.

    Deliberately without an idempotency key: asking for a second link because
    the first one expired is normal, and suppressing it would lock the creator
    out of their own settings.
    """
    subject = f"Dein Anmeldelink für {settings.product.name}"
    html, text = render_pair("magic_link", creator, subject, link=link, settings=settings)
    return OutgoingEmail(
        from_=f"{settings.product.name} <{settings.sender_address}>",
        to=creator.contact_email,
        subject=subject,
        html=html,
        text=text,
        reply_to=settings.support_email,
        tags={"kind": "magic_link"},
    )


def render_confirm_mail(
    creator: Creator, address: str, link: str, settings: Settings
) -> OutgoingEmail:
    """Build the double-opt-in mail, which is also the welcome mail.

    It carries no link to a summary: those pages must not reach an address that
    has not proved it wants them. Without an idempotency key, because asking
    again after a lost mail is exactly what the fan is supposed to do.
    """
    subject = f"Bitte bestätige: Zusammenfassungen von {creator.name}"
    html, text = render_pair("confirm", creator, subject, link=link)
    return OutgoingEmail(
        from_=sender(creator, settings),
        to=address,
        subject=subject,
        html=html,
        text=text,
        reply_to=reply_to(creator, settings),
        tags={"kind": "confirm"},
    )


@dataclass(frozen=True)
class Notice:
    """The German wording for one kind of creator notice."""

    subject: str
    headline: str
    explanation: str
    what_now: str = ""
    action_label: str = ""


#: One entry per reason. Plain German, no exclamation marks: these arrive
#: unannounced and should read like a colleague, not like an alarm. The creator
#: chose this service so they would not have to think about it, so every notice
#: says what happened, what it means, and whether anything is expected of them.
NOTICES = {
    NoticeKind.NO_TRANSCRIPT: Notice(
        subject="Ein Video ohne Untertitel — keine Zusammenfassung möglich",
        headline="Für ein Video gibt es keine Untertitel",
        explanation=(
            "Ohne Untertitel lässt sich nicht zusammenfassen, was gesagt wurde. "
            "Deshalb bekommen deine Abonnenten zu diesem Video keine Mail."
        ),
        what_now=(
            "Wenn du magst, lade Untertitel bei YouTube hoch oder aktiviere die "
            "automatischen — beim nächsten Mal klappt es dann."
        ),
    ),
    NoticeKind.TOO_LONG: Notice(
        subject="Ein Video ist zu lang für eine Zusammenfassung",
        headline="Ein Video ist länger, als wir zusammenfassen können",
        explanation=(
            "Das Transkript überschreitet die eingestellte Höchstlänge. Zu diesem "
            "Video geht keine Mail an deine Abonnenten."
        ),
    ),
    NoticeKind.OAUTH_RECONSENT: Notice(
        subject="Bitte verbinde deinen YouTube-Kanal erneut",
        headline="Die Verbindung zu YouTube ist abgelaufen",
        explanation=(
            "Wir können deine Untertitel gerade nicht mehr offiziell abrufen. "
            "Das passiert, wenn die Freigabe zurückgezogen wurde oder abgelaufen ist."
        ),
        what_now="Ein Klick stellt die Verbindung wieder her.",
        action_label="YouTube neu verbinden",
    ),
    NoticeKind.FAILED: Notice(
        subject="Ein Video konnte nicht verarbeitet werden",
        headline="Ein Video hat es nicht durch die Verarbeitung geschafft",
        explanation=(
            "Wir haben es mehrfach versucht und schauen uns an, woran es lag. "
            "Zu diesem Video geht keine Mail an deine Abonnenten."
        ),
        what_now="Du musst nichts tun — wir melden uns, wenn wir mehr wissen.",
    ),
}


#: The creator fields a rendered mail depends on. Frozen onto the mailing when
#: the preview goes out, so that the fans get exactly the mail the creator saw
#: and a retried batch is byte-identical under its stable idempotency key.
SNAPSHOT_FIELDS = (
    "name",
    "email_variant",
    "greeting_text",
    "farewell_text",
    "reply_to_email",
    "logo_url",
    "accent_color",
)


def snapshot_of(creator: Creator, variant: str) -> dict[str, str | None]:
    """Capture what a rendered mail depends on."""
    frozen = {name: getattr(creator, name) for name in SNAPSHOT_FIELDS}
    frozen["email_variant"] = variant
    return frozen


def as_rendered(creator: Creator, snapshot: dict | None, settings: Settings) -> SimpleNamespace:
    """Return whom to render as: the creator as frozen, or as they are now.

    A plain namespace rather than the ORM object, so that nothing can be written
    through it by accident and no frozen field can silently fall back to a live
    one.
    """
    fields = {name: getattr(creator, name) for name in SNAPSHOT_FIELDS} | (snapshot or {})
    if not snapshot:
        # One rule for "NULL means the file default", and it lives in one place.
        fields["email_variant"] = effective_settings(creator, settings).email_variant
    return SimpleNamespace(
        id=creator.id, slug=creator.slug, contact_email=creator.contact_email, **fields
    )


def jump_link(url: str) -> Callable[[int], str]:
    """Build the function templates use to link into the video at a position."""
    separator = "&" if "?" in url else "?"
    return lambda seconds: f"{url}{separator}t={int(seconds)}s"


def render_summary_mail(
    *,
    creator: Creator,
    appearance,
    summary,
    sentiment,
    subscription,
    settings: Settings,
    view_url: str,
    snapshot: dict | None = None,
    variant: str | None = None,
    stop_token: str = "",
    send_at=None,
    idempotency_key: str | None = None,
) -> OutgoingEmail:
    """Build the mail a fan receives — or the preview of it the creator gets.

    The preview is the same mail, rendered from the same template with the same
    data, plus an action bar. That is the point: a preview that differed from
    what goes out would be worse than no preview at all.

    ``subscription`` is ``None`` exactly for the creator's preview — that one
    fact decides the recipient, the unsubscribe headers and the footer, so it is
    read here rather than passed alongside as a flag that could disagree with it.

    ``variant`` overrides what the creator chose. Only ``cli demo-mails`` passes
    it, to show all three formats from one analysis; the send path leaves it
    alone, so a frozen mailing renders the variant it was previewed with.
    """
    preview = subscription is None
    rendered_as = as_rendered(creator, snapshot, settings)
    context = {
        "appearance": appearance,
        "summary": summary,
        "sentiment": sentiment,
        "subscription": subscription,
        "variant": variant or rendered_as.email_variant,
        "view_url": view_url,
        "jump": jump_link(appearance.url),
        "preview": preview,
        "stop_token": stop_token,
        "send_at": send_at,
        "postpone_hours": settings.schedule.postpone_hours,
    }
    subject = f"{rendered_as.name}: {appearance.title}"
    html, text = render_pair("summary", rendered_as, subject, **context)

    headers = {}
    if subscription is not None:
        unsubscribe = f"{settings.base_url}/abmelden/{subscription.unsubscribe_token}"
        # RFC 8058: the one-click button every serious mail client shows. A fan
        # who cannot leave in one click complains instead, and a complaint costs
        # the sending reputation of every creator on the platform.
        headers["List-Unsubscribe"] = f"<{unsubscribe}>"
        headers["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

    return OutgoingEmail(
        from_=sender(rendered_as, settings),
        to=creator.contact_email if preview else subscription.subscriber.email,
        subject=subject,
        html=html,
        text=text,
        reply_to=reply_to(rendered_as, settings),
        headers=headers,
        idempotency_key=idempotency_key,
        tags={"kind": "preview" if preview else "summary"},
    )
