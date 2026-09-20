"""Every table and every status vocabulary, in one file (plan §7).

Conventions that hold throughout:

- Timestamps are ``timestamptz`` and always UTC; display converts to
  ``product.timezone``.
- A status column is ``VARCHAR`` plus a ``CHECK`` built from its ``StrEnum``,
  never a native Postgres enum: alembic autogenerate mishandles those, and a
  new status value would otherwise need a migration of its own.
- Everything below ``creators`` cascades on delete, so removing a creator or a
  subscriber on request is one SQL statement in the runbook, not a tree walk.
- Ledger rows outlive what they refer to, so their foreign keys null out.
"""

from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Stable, predictable constraint names; without them alembic invents its own and
# a later migration cannot drop what an earlier one created.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

TOKEN_LENGTH = 64  # secrets.token_urlsafe(32) yields 43 characters; room to spare


class Base(DeclarativeBase):
    """Declarative base carrying the naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def one_of(column: str, values: type[enum.StrEnum]) -> CheckConstraint:
    """Build the CHECK constraint that pins a column to its vocabulary.

    Parameters
    ----------
    column
        Name of the column to constrain.
    values
        The ``StrEnum`` whose members are the allowed values.
    """
    allowed = ", ".join(f"'{member.value}'" for member in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=f"{column}_valid")


def timestamp(**kwargs: Any) -> Mapped[datetime]:
    """Build a UTC timestamp column."""
    return mapped_column(DateTime(timezone=True), **kwargs)


def created_at_column() -> Mapped[datetime]:
    """Creation timestamp, set by the database."""
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# --- Vocabularies -----------------------------------------------------------


class SourceKind(enum.StrEnum):
    """Where a source's items come from. Phase 2 adds ``podcast``."""

    YOUTUBE = "youtube"


class AppearanceStatus(enum.StrEnum):
    """Pipeline state of one video (plan §9.1)."""

    DETECTED = "detected"
    ENRICHED = "enriched"
    TRANSCRIBED = "transcribed"
    ANALYZED = "analyzed"
    SKIPPED_SHORT = "skipped_short"
    SKIPPED_NO_TRANSCRIPT = "skipped_no_transcript"
    SKIPPED_TOO_LONG = "skipped_too_long"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class SkipReason(enum.StrEnum):
    """Why a row is waiting in ``detected`` instead of moving on (plan §9.1)."""

    NOT_PUBLIC_YET = "not_public_yet"
    NO_DURATION_YET = "no_duration_yet"


class TranscriptOrigin(enum.StrEnum):
    """Which provider produced a transcript. Stored because it is legally relevant."""

    YOUTUBE_OFFICIAL = "youtube_official"
    YOUTUBE_UNOFFICIAL = "youtube_unofficial"


class AnalysisKind(enum.StrEnum):
    """The two analyses the MVP produces."""

    SUMMARY = "summary"
    SENTIMENT = "sentiment"


class SubscriptionStatus(enum.StrEnum):
    """Double-opt-in state of one fan for one creator."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    UNSUBSCRIBED = "unsubscribed"


class BlockedReason(enum.StrEnum):
    """Why an address receives nothing any more (reported by the mail provider)."""

    BOUNCE = "bounce"
    COMPLAINT = "complaint"


class MailingStatus(enum.StrEnum):
    """Lifecycle of one planned send (plan §9.2)."""

    SCHEDULED = "scheduled"
    SENTIMENT_READY = "sentiment_ready"
    PREVIEW_SENT = "preview_sent"
    SENDING = "sending"
    SENT = "sent"
    STOPPED = "stopped"
    CANCELLED = "cancelled"
    FAILED = "failed"


#: States in which the creator's stop and postpone links still act.
MAILING_STOPPABLE = frozenset(
    {MailingStatus.SCHEDULED, MailingStatus.SENTIMENT_READY, MailingStatus.PREVIEW_SENT}
)


class NoticeKind(enum.StrEnum):
    """Why the creator is being written to (plan §9.3 ``notify_creator``)."""

    NO_TRANSCRIPT = "no_transcript"
    TOO_LONG = "too_long"
    OAUTH_RECONSENT = "oauth_reconsent"
    FAILED = "failed"
    PREVIEW_FAILED = "preview_failed"
    SEND_FAILED = "send_failed"


# --- Tables -----------------------------------------------------------------


class Creator(Base):
    """A paying customer of product 1 (manifest: *Creator*).

    Nullable override columns mean "use the value from ``settings.toml``";
    ``effective_settings(creator)`` is the one place that resolves them.
    """

    __tablename__ = "creators"
    # No CHECK on email_variant: its vocabulary lives in settings.email.variants,
    # so that adding a fourth variant stays one template block and one config line.
    __table_args__ = (
        CheckConstraint("accent_color ~ '^#[0-9a-fA-F]{6}$'", name="accent_color_is_hex"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(320), nullable=False)
    reply_to_email: Mapped[str | None] = mapped_column(String(320))

    logo_url: Mapped[str | None] = mapped_column(Text)
    accent_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#333333")
    greeting_text: Mapped[str | None] = mapped_column(Text)
    farewell_text: Mapped[str | None] = mapped_column(Text)
    email_variant: Mapped[str | None] = mapped_column(String(32))

    send_delay_hours: Mapped[int | None] = mapped_column(Integer)
    min_duration_seconds: Mapped[int | None] = mapped_column(Integer)

    magic_link_token_hash: Mapped[str | None] = mapped_column(String(64))
    magic_link_expires_at: Mapped[datetime | None] = timestamp()

    created_at: Mapped[datetime] = created_at_column()


class Source(Base):
    """A channel belonging to a creator (manifest: *Quelle*).

    Items published before ``created_at`` are back catalogue and are only
    ingested by an explicit backfill.
    """

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("kind", "external_id"),
        one_of("kind", SourceKind),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)

    oauth_refresh_token_enc: Mapped[str | None] = mapped_column(Text)
    oauth_granted_at: Mapped[datetime | None] = timestamp()
    oauth_needs_reconsent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    created_at: Mapped[datetime] = created_at_column()


class Appearance(Base):
    """One video (manifest: *Auftritt*) — the central, source-independent object.

    The unique constraint on ``(source_id, external_id)`` is the idempotency
    guarantee: seeing the same video twice can never create a second row.
    """

    __tablename__ = "appearances"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id"),
        one_of("status", AppearanceStatus),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = timestamp(nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    skip_reason: Mapped[str | None] = mapped_column(Text)
    is_backfill: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    view_token: Mapped[str] = mapped_column(String(TOKEN_LENGTH), unique=True, nullable=False)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime | None] = timestamp()
    last_error: Mapped[str | None] = mapped_column(Text)

    # Set when the official caption provider has said no for this video. Asking
    # it again costs 250 quota units to hear the same answer, and the shared
    # retry counter cannot stand in for this: it is incremented by any step's
    # temporary failure, so an IP block at the unofficial provider would
    # otherwise disable the official one — including for a creator who connects
    # YouTube precisely because the first attempt failed.
    official_captions_declined: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )

    created_at: Mapped[datetime] = created_at_column()


class Transcript(Base):
    """What was said (manifest: *Transkript*).

    Plain text is derived from ``segments`` on read, never stored twice.
    """

    __tablename__ = "transcripts"
    __table_args__ = (one_of("origin", TranscriptOrigin),)

    id: Mapped[int] = mapped_column(primary_key=True)
    appearance_id: Mapped[int] = mapped_column(
        ForeignKey("appearances.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    origin: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    is_generated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = created_at_column()


class Analysis(Base):
    """One LLM result for one appearance (manifest: *Analyse*).

    At most one row per kind, written with ``INSERT … ON CONFLICT DO UPDATE``;
    a sentiment refresh after a postpone overwrites the previous one.

    ``# ponytail: one analysis per kind; keep history when A/B-comparing prompts
    in production becomes a real task.``
    """

    __tablename__ = "analyses"
    __table_args__ = (
        UniqueConstraint("appearance_id", "kind"),
        one_of("kind", AnalysisKind),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    appearance_id: Mapped[int] = mapped_column(
        ForeignKey("appearances.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class Subscriber(Base):
    """An e-mail address (manifest: *Abonnent*), possibly following several creators.

    Blocked rows are kept deliberately: they are the suppression list. A
    ``complaint`` block is permanent; a ``bounce`` block is lifted when the
    address later confirms a sign-up, because that mail evidently arrived.
    """

    __tablename__ = "subscribers"
    __table_args__ = (one_of("blocked_reason", BlockedReason),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Always written lower-cased, so the unique constraint is the identity rule.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    blocked_at: Mapped[datetime | None] = timestamp()
    blocked_reason: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = created_at_column()


class Subscription(Base):
    """One fan's double-opt-in state for one creator.

    Unsubscribing is per creator, which is what the multi-creator data model
    implies; a global "stop everything" arrives with the fan dashboard.
    """

    __tablename__ = "subscriptions"
    __table_args__ = (
        UniqueConstraint("subscriber_id", "creator_id"),
        one_of("status", SubscriptionStatus),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("creators.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    confirm_token: Mapped[str | None] = mapped_column(String(TOKEN_LENGTH), unique=True)
    confirm_expires_at: Mapped[datetime | None] = timestamp()
    # Throttles confirm mails per address, independently of the per-IP limit.
    confirm_sent_at: Mapped[datetime | None] = timestamp()
    confirmed_at: Mapped[datetime | None] = timestamp()

    # The one relationship in the schema. Composing a mail needs the address
    # behind the subscription, and spelling that as a second query in every
    # caller is how a caller eventually forgets.
    subscriber: Mapped[Subscriber] = relationship(lazy="joined")

    # Permanent: an unsubscribe link must work for as long as mails exist.
    unsubscribe_token: Mapped[str] = mapped_column(
        String(TOKEN_LENGTH), unique=True, nullable=False
    )
    unsubscribed_at: Mapped[datetime | None] = timestamp()

    created_at: Mapped[datetime] = created_at_column()


class Mailing(Base):
    """One planned send for one appearance (manifest: *Zustellung*, the planned part)."""

    __tablename__ = "mailings"
    __table_args__ = (one_of("status", MailingStatus),)

    id: Mapped[int] = mapped_column(primary_key=True)
    appearance_id: Mapped[int] = mapped_column(
        ForeignKey("appearances.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    send_at: Mapped[datetime] = timestamp(nullable=False, index=True)

    # Rotated on every new schedule, so older preview links die with it.
    stop_token: Mapped[str] = mapped_column(String(TOKEN_LENGTH), unique=True, nullable=False)
    preview_sent_at: Mapped[datetime | None] = timestamp()

    # The creator's rendering-relevant fields, frozen when the preview goes out:
    # the fans get exactly the mail he saw and did not stop, and a retried batch
    # carries a byte-identical payload under its stable idempotency key.
    # `none_as_null`: clearing it must write SQL NULL, not a stored JSON "null",
    # or every `IS NULL` query quietly misses the rows that were cleared.
    render_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True))

    stopped_at: Mapped[datetime | None] = timestamp()
    sent_at: Mapped[datetime | None] = timestamp()
    recipient_count: Mapped[int | None] = mapped_column(Integer)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime | None] = timestamp()
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = created_at_column()


class Delivery(Base):
    """One recipient of one mailing — a send ledger, not analytics.

    The unique constraint is the exactly-once guarantee per recipient.

    ``# ponytail: no delivered/bounced state and no provider message id;
    bounces block the subscriber by address, and delivery and open rates come
    from the provider's dashboard. Add columns with the analytics dashboard.``
    """

    __tablename__ = "deliveries"
    __table_args__ = (UniqueConstraint("mailing_id", "subscription_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    mailing_id: Mapped[int] = mapped_column(
        ForeignKey("mailings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Indexed for the cascade: deleting a subscription (cleanup, a fan's
    # erasure request) must not scan every delivery ever sent.
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sent_at: Mapped[datetime | None] = timestamp()


class LLMCall(Base):
    """Cost ledger (manifest §7.9 "Kostenkontrolle").

    Written in its own committed session, also on failure: a rolled-back step
    must not roll back the record of what it already paid for.
    """

    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    creator_id: Mapped[int | None] = mapped_column(
        ForeignKey("creators.id", ondelete="SET NULL"), index=True
    )
    appearance_id: Mapped[int | None] = mapped_column(
        ForeignKey("appearances.id", ondelete="SET NULL")
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_cents: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, server_default="0")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = created_at_column()


class JobRun(Base):
    """When each periodic job last ran. This replaces a queue's cron tables."""

    __tablename__ = "job_runs"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_run_at: Mapped[datetime] = timestamp(nullable=False)
