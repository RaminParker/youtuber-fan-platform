"""Transport for outgoing mail. Composition happens in ``render.py``.

Two endpoints and a signature check; the provider's SDK would add a dependency
for that. This module knows nothing about creators, mailings or templates — it
takes an :class:`~app.delivery.render.OutgoingEmail` and posts it.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import time
from typing import NoReturn

import httpx

from app import log
from app.delivery.render import OutgoingEmail
from app.errors import TemporaryError

API_BASE = "https://api.resend.com"
TIMEOUT_SECONDS = 30

#: The provider's own ceiling for one batch call.
BATCH_SIZE = 100

logger = log.get_logger(__name__)


class EmailError(Exception):
    """The provider refused the message and will refuse it again."""


class EmailTemporaryError(TemporaryError):
    """The provider was unwell or rate-limited. Worth trying again."""


class QuotaExhausted(EmailTemporaryError):
    """The daily or monthly send allowance is used up.

    Temporary in the sense that tomorrow it will not be, but it needs an
    operator rather than patience — the retry ladder is not going to fix a plan
    limit.
    """


#: The window a webhook signature stays valid for. Longer would make a captured
#: request replayable for longer; shorter would trip over ordinary clock skew.
WEBHOOK_TOLERANCE_SECONDS = 5 * 60


def to_payload(mail: OutgoingEmail) -> dict:
    """Map one mail to the provider's request body."""
    payload = {
        "from": mail.from_,
        "to": [mail.to],
        "subject": mail.subject,
        "html": mail.html,
        "text": mail.text,
    }
    if mail.reply_to:
        payload["reply_to"] = mail.reply_to
    if mail.headers:
        payload["headers"] = mail.headers
    if mail.tags:
        payload["tags"] = [{"name": k, "value": v} for k, v in mail.tags.items()]
    return payload


class ResendClient:
    """Posts mails. Nothing else."""

    def __init__(self, api_key: str, client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._http = client or httpx.Client(timeout=TIMEOUT_SECONDS)

    def send(self, mail: OutgoingEmail) -> str:
        """Send one mail and return the provider's id for it.

        The idempotency key, when the caller set one, is what makes a retry
        after a lost response safe: the provider recognises the repeat and does
        not deliver twice.
        """
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if mail.idempotency_key:
            headers["Idempotency-Key"] = mail.idempotency_key

        try:
            response = self._http.post(f"{API_BASE}/emails", json=to_payload(mail), headers=headers)
        except httpx.HTTPError as error:
            raise EmailTemporaryError(str(error)) from error

        if response.is_success:
            return response.json().get("id", "")
        self._raise_for(response)

    @staticmethod
    def _raise_for(response: httpx.Response) -> NoReturn:
        """Separate "try later" from "this will never work"."""
        if response.status_code == 429:
            raise _rate_limit_error(response)
        if response.status_code >= 500:
            raise EmailTemporaryError(f"HTTP {response.status_code}")
        logger.error(log.EMAIL_REFUSED, status=response.status_code, body=response.text[:500])
        raise EmailError(f"HTTP {response.status_code}: {response.text[:200]}")

    def send_batch(self, mails: list[OutgoingEmail]) -> list[str]:
        """Send up to ``BATCH_SIZE`` mails in one call, in order.

        Strict by design: any refusal fails the whole batch, nothing is marked
        as sent, and the step retries. The alternative — quietly delivering the
        acceptable ones — would leave the ledger disagreeing with reality, and
        the ledger is what makes "exactly once" true.

        ``# ponytail: one address that passes sign-up validation but is rejected
        by the provider blocks the mailing until the operator blocks that
        subscriber; add per-address handling only if that actually happens.``
        """
        if not mails:
            return []
        if len(mails) > BATCH_SIZE:
            raise ValueError(f"batch of {len(mails)} exceeds the limit of {BATCH_SIZE}")

        headers = {"Authorization": f"Bearer {self._api_key}"}
        # One key for the whole batch: a crash between the call and the commit
        # cannot double-send, because the repeat is recognised.
        if mails[0].idempotency_key:
            headers["Idempotency-Key"] = mails[0].idempotency_key

        try:
            response = self._http.post(
                f"{API_BASE}/emails/batch",
                json=[to_payload(mail) for mail in mails],
                headers=headers,
            )
        except httpx.HTTPError as error:
            raise EmailTemporaryError(str(error)) from error

        if response.is_success:
            return [item.get("id", "") for item in response.json().get("data", [])]
        self._raise_for(response)


def _rate_limit_error(response: httpx.Response) -> EmailTemporaryError:
    """Tell a passing rate limit apart from an exhausted plan.

    Both arrive as 429. The first clears in a second; the second needs somebody
    to notice, so it is logged at error level and named differently.
    """
    try:
        name = response.json().get("name", "")
    except ValueError:
        name = ""
    if name in ("daily_quota_exceeded", "monthly_quota_exceeded"):
        logger.error(log.EMAIL_QUOTA_EXHAUSTED, name=name)
        return QuotaExhausted(name)
    return EmailTemporaryError(f"rate limited: {name or 'unknown'}")


def verify_webhook_signature(
    body: bytes, headers: dict[str, str], secret: str, now: float | None = None
) -> bool:
    """Check a provider webhook signature.

    Fifteen lines of standard library rather than a dependency. Three things
    have to hold: the timestamp is recent, the signature is over the raw bytes
    (not the re-serialised JSON), and the comparison is constant-time.

    Parameters
    ----------
    body
        The request body exactly as received.
    headers
        Needs ``svix-id``, ``svix-timestamp`` and ``svix-signature``.
    secret
        The endpoint secret, in its ``whsec_`` form.
    now
        For tests. Defaults to the current time.
    """
    lowered = {key.lower(): value for key, value in headers.items()}
    message_id = lowered.get("svix-id", "")
    timestamp = lowered.get("svix-timestamp", "")
    signatures = lowered.get("svix-signature", "")
    if not (message_id and timestamp and signatures):
        return False

    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    if abs((now if now is not None else time.time()) - sent_at) > WEBHOOK_TOLERANCE_SECONDS:
        return False

    try:
        key = base64.b64decode(secret.removeprefix("whsec_"), validate=True)
    except (binascii.Error, ValueError):
        key = b""
    if not key:
        # A missing or malformed secret must reject, like every other failure
        # here. An empty one decodes to an empty HMAC key without complaint —
        # and anyone can sign with that.
        logger.error(log.WEBHOOK_SECRET_UNUSABLE)
        return False
    signed = f"{message_id}.{timestamp}.".encode() + body
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest())

    # The header may carry several space-separated versioned signatures; any one
    # of the v1 entries matching is enough. Compared as bytes: a header is
    # attacker-controlled, and comparing non-ASCII strings raises.
    return any(
        hmac.compare_digest(expected, candidate.split(",", 1)[1].encode())
        for candidate in signatures.split()
        if candidate.startswith("v1,")
    )
