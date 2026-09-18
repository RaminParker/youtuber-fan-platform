"""What the mail provider tells us: addresses that bounced, complained, or are suppressed.

Each blocks the address for every creator, because a bad address hurts the
sending reputation the whole platform shares (manifest §6.1, §11). A block is
permanent, like the provider's own suppression list it mirrors.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response
from sqlalchemy import update
from sqlalchemy.sql import func
from starlette.concurrency import run_in_threadpool

from app import log
from app.addresses import canonical
from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import BlockedReason, Subscriber
from app.delivery.email_client import verify_webhook_signature

router = APIRouter(tags=["webhooks"])
logger = log.get_logger(__name__)


@router.post("/webhooks/resend")
async def handle_resend_webhook(request: Request) -> Response:
    """Verify the signature, then block what the event says to block.

    ``async`` only to read the raw body: the signature is over the exact bytes,
    not over re-serialised JSON. The database write runs in the threadpool.

    A bad signature gets 401: with a wrong or missing secret configured, the
    provider's dashboard then shows the failures and retries, instead of every
    bounce vanishing behind a 200. Anything signed gets 200, including events
    of a shape we do not expect — a retry would not reshape them. No dedup
    table: every write is set-to-value, so the provider's at-least-once
    delivery and dashboard replays change nothing.
    """
    body = await request.body()
    if not verify_webhook_signature(
        body, dict(request.headers), get_settings().secrets.resend_webhook_secret
    ):
        logger.warning(log.WEBHOOK_RESEND, signature_ok=False)
        return Response(status_code=401)

    event = _object(_parse(body))
    data = _object(event.get("data"))
    logger.info(log.WEBHOOK_RESEND, type=event.get("type"), signature_ok=True)

    reason = _blocking_reason(event.get("type"), data)
    addresses = _recipients(data)
    if reason is not None and addresses:
        await run_in_threadpool(block_addresses, addresses, reason)
    return Response(status_code=200)


def _parse(body: bytes) -> object:
    try:
        return json.loads(body)
    except ValueError:
        return None


def _object(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _recipients(data: dict) -> list[str]:
    to = data.get("to")
    if not isinstance(to, list):
        return []
    return [canonical(address) for address in to if isinstance(address, str)]


def _blocking_reason(event_type: object, data: dict) -> BlockedReason | None:
    """Only a permanent bounce blocks; a full mailbox or a greylisting does not."""
    if event_type == "email.complained":
        return BlockedReason.COMPLAINT
    if event_type == "email.suppressed":
        # The provider skipped the send: the address is on its account-wide
        # list, from a bounce this database may since have forgotten.
        return BlockedReason.BOUNCE
    if event_type == "email.bounced" and _object(data.get("bounce")).get("type") == "Permanent":
        return BlockedReason.BOUNCE
    return None


def block_addresses(addresses: list[str], reason: BlockedReason) -> None:
    """Block the subscribers behind these addresses; unknown ones are ignored.

    Only rows that change are touched: an unblocked address gets blocked, and
    a bounce block becomes a complaint block — a complaint outranks a bounce,
    never the other way round. The first block's date is kept. A replay
    therefore matches nothing, and nothing is logged twice.
    """
    changes = Subscriber.blocked_at.is_(None)
    if reason == BlockedReason.COMPLAINT:
        changes |= Subscriber.blocked_reason != BlockedReason.COMPLAINT

    with session_scope() as session:
        blocked = session.scalars(
            update(Subscriber)
            .where(Subscriber.email.in_(addresses), changes)
            .values(
                blocked_at=func.coalesce(Subscriber.blocked_at, func.now()),
                blocked_reason=reason,
            )
            .returning(Subscriber.id)
        ).all()
    for subscriber_id in blocked:
        logger.info(log.SUBSCRIBER_BLOCKED, subscriber_id=subscriber_id, reason=reason)
