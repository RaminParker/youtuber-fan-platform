"""What the mail provider tells us: addresses that bounced or complained.

Both block the address for every creator, because a bad address hurts the
sending reputation the whole platform shares (manifest §6.1, §11).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response
from sqlalchemy import case, func, update
from starlette.concurrency import run_in_threadpool

from app import log
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

    Always 200. The provider delivers at least once and retries anything else;
    a forged or unreadable request has earned no explanation. No dedup table
    either: every write is set-to-value, so a replay changes nothing.
    """
    body = await request.body()
    signature_ok = verify_webhook_signature(
        body, dict(request.headers), get_settings().secrets.resend_webhook_secret
    )
    event = _parse(body) if signature_ok else {}
    report = logger.info if signature_ok else logger.warning
    report(log.WEBHOOK_RESEND, type=event.get("type"), signature_ok=signature_ok)
    reason = _blocking_reason(event)
    if reason is not None:
        addresses = [address.strip().lower() for address in event["data"].get("to", [])]
        await run_in_threadpool(block_addresses, addresses, reason)
    return Response(status_code=200)


def _parse(body: bytes) -> dict:
    try:
        event = json.loads(body)
    except ValueError:
        return {}
    return event if isinstance(event, dict) else {}


def _blocking_reason(event: dict) -> BlockedReason | None:
    """Only a permanent bounce blocks; a full mailbox or a greylisting does not."""
    data = event.get("data") or {}
    if event.get("type") == "email.complained":
        return BlockedReason.COMPLAINT
    if (
        event.get("type") == "email.bounced"
        and (data.get("bounce") or {}).get("type") == "Permanent"
    ):
        return BlockedReason.BOUNCE
    return None


def block_addresses(addresses: list[str], reason: BlockedReason) -> None:
    """Block the subscribers behind these addresses; unknown ones are ignored.

    The first block's date is kept. A complaint outranks a bounce: the next
    confirmation lifts a bounce block, and a person who reported spam must
    never be written to again.
    """
    with session_scope() as session:
        result = session.execute(
            update(Subscriber)
            .where(Subscriber.email.in_(addresses))
            .values(
                blocked_at=func.coalesce(Subscriber.blocked_at, func.now()),
                blocked_reason=case(
                    (Subscriber.blocked_reason == BlockedReason.COMPLAINT, BlockedReason.COMPLAINT),
                    else_=reason,
                ),
            )
            .returning(Subscriber.id)
        )
        for subscriber_id in result.scalars():
            logger.info(log.SUBSCRIBER_BLOCKED, subscriber_id=subscriber_id, reason=reason)
