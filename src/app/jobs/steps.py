"""The pipeline steps and the periodic jobs.

Every step follows the same shape: read the row, do one thing, write the new
status. Steps are thin — the work itself belongs to the layer that owns it —
and they never call ``datetime.now()``: ``now`` arrives as a parameter, which
is what makes a seven-day schedule testable in milliseconds.

Appearance status is written here and only here.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app import log
from app.analysis.comments import filter_comments
from app.analysis.llm import assert_under_cap, record_call
from app.analysis.sentiment import PURPOSE as SENTIMENT_PURPOSE
from app.analysis.sentiment import analyse_sentiment
from app.analysis.summarize import PURPOSE as SUMMARY_PURPOSE
from app.analysis.summarize import TranscriptTooLong, summarise
from app.config import Settings, get_settings
from app.creator_settings import effective_settings
from app.db.engine import session_scope
from app.db.models import (
    Analysis,
    AnalysisKind,
    Appearance,
    AppearanceStatus,
    BlockedReason,
    Creator,
    JobRun,
    NoticeKind,
    SkipReason,
    Source,
    Subscriber,
    Subscription,
    SubscriptionStatus,
    Transcript,
    TranscriptOrigin,
)
from app.delivery.mailing import schedule_mailing
from app.delivery.render import render_notice_mail
from app.errors import TemporaryError
from app.jobs.schedule import WAIT_FOR_THE_WORLD
from app.services import get_services
from app.sources.base import ContentItem
from app.sources.youtube import feed as youtube_feed
from app.tokens import new_token
from app.transcripts import service as transcript_service
from app.transcripts.base import (
    Segment,
    TranscriptProvider,
    TranscriptTemporaryError,
    TranscriptUnavailable,
)

POLL_FEEDS = "poll_feeds"
CLEANUP = "cleanup"

logger = log.get_logger(__name__)


def ingest_item(
    session: Session,
    source: Source,
    *,
    external_id: str,
    title: str,
    url: str,
    published_at: datetime,
    allow_backlog: bool = False,
) -> Appearance | None:
    """Record one item as ``detected``, unless it is back catalogue we may skip.

    Whether something is back catalogue is derived from the data, never from the
    caller: an item published before the source existed is back catalogue, full
    stop. A first poll must therefore never mail the archive, while an explicit
    backfill may still ingest it.

    The insert is ``ON CONFLICT DO NOTHING`` against the unique
    ``(source_id, external_id)``. That constraint — not application logic — is
    the idempotency guarantee: seeing the same video twice cannot create a
    second row, however the two calls interleave.

    Returns
    -------
    Appearance or None
        The row, or ``None`` when the item was skipped as backlog or already
        existed.
    """
    is_backfill = published_at < source.created_at
    if is_backfill and not allow_backlog:
        return None

    result = session.execute(
        insert(Appearance)
        .values(
            source_id=source.id,
            external_id=external_id,
            title=title,
            url=url,
            published_at=published_at,
            status=AppearanceStatus.DETECTED,
            is_backfill=is_backfill,
            view_token=new_token(),
        )
        .on_conflict_do_nothing(index_elements=["source_id", "external_id"])
        .returning(Appearance)
    )
    appearance = result.scalar_one_or_none()
    if appearance is not None:
        logger.info(
            log.ITEM_DETECTED,
            appearance_id=appearance.id,
            external_id=external_id,
            is_backfill=is_backfill,
        )
    return appearance


def enrich(session: Session, appearance_id: int, now: datetime) -> None:
    """Fill in what the feed could not say, and decide whether to go on.

    The feed knows a title and a date. Whether the item is public, how long it
    is and whether it is a premiere that has not started all cost one quota unit
    to find out — and all three can change the outcome.
    """
    settings = get_settings()
    appearance = session.get(Appearance, appearance_id)
    if appearance is None or appearance.status != AppearanceStatus.DETECTED:
        return

    source = session.get(Source, appearance.source_id)
    creator = session.get(Creator, source.creator_id)
    items = get_services().youtube.item_details([appearance.external_id])

    if not items:
        _terminate(appearance, AppearanceStatus.UNAVAILABLE, reason="deleted")
        return

    item = items[0]
    if not item.is_public or item.is_live_or_upcoming:
        _wait_for_the_world(appearance, SkipReason.NOT_PUBLIC_YET, now)
        return

    # A livestream recording reports PT0S until YouTube has finished processing
    # it. That is "unknown", not "short" — and mistaking the two would drop the
    # recording into a terminal state, silently and without a notice.
    if not item.duration_seconds:
        _wait_for_the_world(appearance, SkipReason.NO_DURATION_YET, now)
        return

    _apply_details(appearance, item, source)

    minimum = effective_settings(creator, settings).min_duration_seconds
    if item.duration_seconds < minimum:
        _terminate(appearance, AppearanceStatus.SKIPPED_SHORT, reason="below_minimum_duration")
        return

    appearance.status = AppearanceStatus.ENRICHED
    appearance.skip_reason = None
    appearance.attempts = 0
    appearance.next_attempt_at = None


def _apply_details(appearance: Appearance, item: ContentItem, source: Source) -> None:
    """Overwrite the feed's provisional values with the authoritative ones.

    ``published_at`` matters most: for a premiere it becomes the moment the
    broadcast actually started. Which is also why ``is_backfill`` is decided
    again here — a premiere announced before the creator was onboarded but going
    live afterwards is a normal upload and must be mailed, not filed away as
    archive.
    """
    appearance.title = item.title
    appearance.url = item.url
    appearance.published_at = item.published_at
    appearance.duration_seconds = item.duration_seconds
    if appearance.is_backfill and item.published_at >= source.created_at:
        appearance.is_backfill = False


def _wait_for_the_world(appearance: Appearance, reason: SkipReason, now: datetime) -> None:
    """Park a row until reality catches up.

    Not an error and not an attempt: a premiere three weeks out is exactly the
    video a creator promotes most, and it should still be waiting when it
    starts. The row leaves ``detected`` only once the item is public or gone.
    """
    appearance.skip_reason = reason
    appearance.next_attempt_at = now + WAIT_FOR_THE_WORLD
    logger.info(
        log.ITEM_SKIPPED,
        appearance_id=appearance.id,
        reason=reason,
        retry_at=appearance.next_attempt_at,
    )


def _terminate(appearance: Appearance, status: AppearanceStatus, *, reason: str) -> None:
    """Move a row to a state the pipeline will never revisit."""
    appearance.status = status
    appearance.skip_reason = reason
    appearance.next_attempt_at = None
    logger.info(log.ITEM_SKIPPED, appearance_id=appearance.id, status=status, reason=reason)


def mark_failed(appearance: Appearance) -> None:
    """End a row the pipeline could not get through.

    Lives here, with the other terminal writes, so that this module's promise —
    appearance status is written here and only here — stays true. The worker
    decides *that* a row is finished; where that is recorded is this module's
    business.
    """
    appearance.status = AppearanceStatus.FAILED
    appearance.next_attempt_at = None


def poll_feeds(session: Session, now: datetime) -> int:
    """Ask every source's public feed whether something new appeared.

    ``# ponytail: the six-hourly poll is the only upload trigger; add
    PubSubHubbub push when a creator needs sub-hour detection.``

    Returns
    -------
    int
        How many new appearances were recorded.
    """
    new_items = 0
    # One connection for every source in this run, instead of a TLS handshake
    # per channel per poll.
    with httpx.Client(timeout=youtube_feed.TIMEOUT_SECONDS) as client:
        for source in session.scalars(select(Source)):
            try:
                entries = youtube_feed.fetch_feed(source.external_id, client)
            except TemporaryError as error:
                # One unreachable channel must not cost the other channels
                # their poll.
                logger.warning(log.FEED_POLLED, source_id=source.id, error=str(error))
                continue

            ingested = [
                ingest_item(
                    session,
                    source,
                    external_id=entry.video_id,
                    title=entry.title,
                    url=entry.url,
                    published_at=entry.published_at,
                )
                for entry in entries
            ]
            found = sum(1 for appearance in ingested if appearance is not None)
            new_items += found
            logger.info(log.FEED_POLLED, source_id=source.id, entries=len(entries), new=found)

    return new_items


def cleanup(session: Session, now: datetime, settings: Settings) -> None:
    """Delete what we have no reason to keep (manifest §7.9, plan §13).

    Sign-ups never confirmed, and unsubscriptions past their retention. Then
    every address left without a subscription — except a complaint: a person
    who reported spam must never be written to again, and the row is what
    stops a new sign-up. A bounced address has nothing left to protect; the
    mail provider keeps its own suppression entry for it.

    An address a sign-up is holding right now is skipped (``SKIP LOCKED``):
    deleting it would cascade into the subscription being added. Tomorrow's
    run gets it, if it is still an orphan then.

    The re-check of deleted videos joins this job with the send path (M6).
    """
    retention = timedelta(days=settings.email.unsubscribed_retention_days)
    expired = session.execute(
        delete(Subscription).where(
            (
                (Subscription.status == SubscriptionStatus.PENDING)
                & (Subscription.confirm_expires_at < now)
            )
            | (
                (Subscription.status == SubscriptionStatus.UNSUBSCRIBED)
                & (Subscription.unsubscribed_at < now - retention)
            )
        )
    ).rowcount
    orphans = (
        select(Subscriber.id)
        .where(
            Subscriber.blocked_reason.is_distinct_from(BlockedReason.COMPLAINT),
            ~select(Subscription.id).where(Subscription.subscriber_id == Subscriber.id).exists(),
        )
        .with_for_update(skip_locked=True)
    )
    deleted = session.execute(delete(Subscriber).where(Subscriber.id.in_(orphans))).rowcount
    logger.info(log.CLEANUP_DONE, subscriptions=expired, subscribers=deleted)


def job_is_due(session: Session, name: str, now: datetime, every: timedelta) -> bool:
    """Whether a periodic job has waited long enough to run again."""
    run = session.get(JobRun, name)
    return run is None or run.last_run_at + every <= now


def record_run(session: Session, name: str, now: datetime) -> None:
    """Remember that a periodic job ran. This replaces a queue's cron table."""
    session.execute(
        insert(JobRun)
        .values(name=name, last_run_at=now)
        .on_conflict_do_update(index_elements=["name"], set_={"last_run_at": now})
    )


def notify_creator(creator: Creator, kind: NoticeKind, **context) -> None:
    """Tell the creator that something needs their attention, or simply happened.

    Failures here are swallowed on purpose: a notice that cannot be delivered
    must not turn a handled situation into an unhandled one. The step that
    called this has already done its job.
    """
    settings = get_settings()
    mail = render_notice_mail(creator, kind, settings, **context)
    try:
        get_services().email.send(mail)
    except Exception:
        logger.exception(log.CREATOR_NOTICE_FAILED, creator_id=creator.id, kind=kind)


def transcribe(session: Session, appearance_id: int, now: datetime) -> None:
    """Fetch the transcript, or decide that there will never be one.

    The official provider is offered only on the first attempt. It costs 250
    quota units, and a provider that has already declined this video will
    decline it again — ten attempts would spend 2,500 units to learn nothing.
    """
    settings = get_settings()
    appearance = session.get(Appearance, appearance_id)
    if appearance is None or appearance.status != AppearanceStatus.ENRICHED:
        return

    source = session.get(Source, appearance.source_id)
    creator = session.get(Creator, source.creator_id)
    providers = _providers_for(source, appearance)
    grant_was_fine = not source.oauth_needs_reconsent
    declined: set[str] = set()

    try:
        transcript = transcript_service.fetch_transcript(
            source,
            _as_content_item(appearance),
            providers,
            settings.content.transcript_languages,
            declined,
        )
    except TranscriptTemporaryError:
        # Nothing else survives this rollback, but the 250-unit lesson should.
        _remember_declines(appearance.id, declined)
        raise
    except TranscriptUnavailable as error:
        _remember_declines(appearance.id, declined)
        _terminate(appearance, AppearanceStatus.SKIPPED_NO_TRANSCRIPT, reason=error.reason)
        notify_creator(
            creator,
            NoticeKind.NO_TRANSCRIPT,
            video_title=appearance.title,
            appearance_id=appearance.id,
        )
        _notify_if_the_grant_just_died(source, creator, grant_was_fine, settings)
        return

    _remember_declines(appearance.id, declined)
    _notify_if_the_grant_just_died(source, creator, grant_was_fine, settings)

    session.add(
        Transcript(
            appearance_id=appearance.id,
            origin=transcript.origin,
            language=transcript.language,
            is_generated=transcript.is_generated,
            segments=transcript.as_json(),
            fetched_at=now,
        )
    )
    appearance.status = AppearanceStatus.TRANSCRIBED
    appearance.attempts = 0
    appearance.next_attempt_at = None
    appearance.last_error = None


def _notify_if_the_grant_just_died(
    source: Source, creator: Creator, grant_was_fine: bool, settings: Settings
) -> None:
    """Tell the creator their YouTube grant is gone — once, and only if it sticks.

    Deliberately called on the two paths that commit, and not from a ``finally``:
    on a temporary failure the step's transaction is rolled back, taking the
    flag and any rotated refresh token with it. A notice sent from ``finally``
    would then report a state that was never saved, and the next video would
    report it all over again.
    """
    if not (grant_was_fine and source.oauth_needs_reconsent):
        return
    notify_creator(
        creator,
        NoticeKind.OAUTH_RECONSENT,
        action_url=f"{settings.base_url}/creator/youtube/verbinden",
    )


def _providers_for(source: Source, appearance: Appearance) -> list[TranscriptProvider]:
    """Decide which providers are worth asking for this row, right now.

    The official one costs 250 quota units, so it is offered while there is a
    grant to use and it has not already declined this video. Both conditions
    can change between attempts — a creator can connect YouTube after the first
    failure, and that is exactly when they most expect it to be used.
    """
    providers = get_services().transcripts
    worth_asking = (
        bool(source.oauth_refresh_token_enc) and not appearance.official_captions_declined
    )
    if worth_asking:
        return list(providers)
    return [p for p in providers if p.origin != TranscriptOrigin.YOUTUBE_OFFICIAL]


def _remember_declines(appearance_id: int, declined: set[str]) -> None:
    """Persist an official decline, if there was one."""
    if TranscriptOrigin.YOUTUBE_OFFICIAL in declined:
        remember_official_decline(appearance_id)


def remember_official_decline(appearance_id: int) -> None:
    """Record that official captions are not available for this video.

    In a session of its own, like the cost ledger and for the same reason: the
    step may be about to roll back, and this fact has to outlive that — it is
    the whole point of not paying 250 units again on the next attempt.
    """
    with session_scope() as session:
        appearance = session.get(Appearance, appearance_id)
        if appearance is not None:
            appearance.official_captions_declined = True


def _as_content_item(appearance: Appearance) -> ContentItem:
    """Rebuild the connector's view of a row, which is what a provider expects."""
    return ContentItem(
        external_id=appearance.external_id,
        title=appearance.title,
        url=appearance.url,
        published_at=appearance.published_at,
        duration_seconds=appearance.duration_seconds,
        is_public=True,
        is_live_or_upcoming=False,
        comments_disabled=False,
    )


def summarize(session: Session, appearance_id: int, now: datetime) -> None:
    """Turn the transcript into a summary, and plan when the mail goes out.

    A back catalogue item takes a different path at the end: it gets its
    sentiment now rather than two hours before a send, because there is no send
    to wait for and its comments are long since final.
    """
    settings = get_settings()
    appearance = session.get(Appearance, appearance_id)
    if appearance is None or appearance.status != AppearanceStatus.TRANSCRIBED:
        return

    source = session.get(Source, appearance.source_id)
    creator = session.get(Creator, source.creator_id)
    transcript = session.scalar(select(Transcript).where(Transcript.appearance_id == appearance.id))

    assert_under_cap(session, creator.id, now, settings)

    segments = [Segment(**segment) for segment in transcript.segments]
    # One description of the call, so the failure and the success branch can
    # never book a different model or prompt version for the same request.
    booking = dict(
        purpose=SUMMARY_PURPOSE,
        model=settings.llm.model_summary,
        prompt_version=settings.llm.summary_prompt_version,
        creator_id=creator.id,
        appearance_id=appearance.id,
        settings=settings,
    )

    try:
        completion = summarise(
            get_services().llm,
            segments,
            title=appearance.title,
            channel=creator.name,
            settings=settings,
        )
    except TranscriptTooLong:
        _terminate(appearance, AppearanceStatus.SKIPPED_TOO_LONG, reason="transcript_too_long")
        notify_creator(
            creator,
            NoticeKind.TOO_LONG,
            video_title=appearance.title,
            appearance_id=appearance.id,
        )
        return
    except Exception as error:
        record_call(**booking, error=error)
        raise

    record_call(**booking, completion=completion)
    _upsert_analysis(
        session,
        appearance.id,
        AnalysisKind.SUMMARY,
        completion,
        settings.llm.summary_prompt_version,
    )

    appearance.status = AppearanceStatus.ANALYZED
    appearance.attempts = 0
    appearance.next_attempt_at = None
    appearance.last_error = None

    if appearance.is_backfill:
        _sentiment_now(session, appearance, source, creator, settings)
        return

    effective = effective_settings(creator, settings)
    schedule_mailing(
        session,
        appearance,
        delay_hours=effective.send_delay_hours,
        min_delay_hours=settings.schedule.min_delay_hours,
        now=now,
    )


def _sentiment_now(
    session: Session,
    appearance: Appearance,
    source: Source,
    creator: Creator,
    settings: Settings,
) -> None:
    """Add the comment picture to a back catalogue item, right away.

    Any failure here is logged and dropped: the summary page is the point, the
    sentiment box is a bonus, and an old video is not worth a retry ladder.
    """
    try:
        raw = get_services().youtube.comments(appearance.external_id, settings.comments.max_count)
        kept = filter_comments(raw, settings.comments, channel_id=source.external_id)
        if not kept:
            return
        completion = analyse_sentiment(
            get_services().llm, kept, title=appearance.title, settings=settings
        )
    except Exception as error:
        logger.warning(
            log.MAILING_SENTIMENT_SKIPPED, appearance_id=appearance.id, reason=str(error)
        )
        return

    record_call(
        purpose=SENTIMENT_PURPOSE,
        model=settings.llm.model_sentiment,
        prompt_version=settings.llm.sentiment_prompt_version,
        creator_id=creator.id,
        appearance_id=appearance.id,
        settings=settings,
        completion=completion,
    )
    _upsert_analysis(
        session,
        appearance.id,
        AnalysisKind.SENTIMENT,
        completion,
        settings.llm.sentiment_prompt_version,
    )


def _upsert_analysis(
    session: Session, appearance_id: int, kind: AnalysisKind, completion, prompt_version: str
) -> None:
    """Write the analysis, replacing any previous one of the same kind.

    One current analysis per kind: a sentiment refreshed after a postpone
    replaces the stale one rather than accumulating beside it.
    """
    # Serialised once; a Summary carries nested sections and key points.
    content = completion.result.model_dump(mode="json")
    session.execute(
        insert(Analysis)
        .values(
            appearance_id=appearance_id,
            kind=kind,
            prompt_version=prompt_version,
            model=completion.model,
            content=content,
        )
        .on_conflict_do_update(
            index_elements=["appearance_id", "kind"],
            set_={"prompt_version": prompt_version, "model": completion.model, "content": content},
        )
    )
