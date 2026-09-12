"""The LLM gateway, the cost ledger and the daily cap.

The gateway is the second of the two abstractions the manifest asks for. The
application speaks plain OpenAI-compatible HTTP and never imports a provider
SDK, so swapping the model — or the provider, or the gateway itself — is a
configuration change.

This module knows nothing about videos, creators or mails. It sends text and
returns a validated object.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select

from app import log
from app.config import Settings
from app.db.engine import session_scope
from app.db.models import LLMCall
from app.errors import CostCapExceeded, TemporaryError

COMPLETIONS_PATH = "/v1/chat/completions"

#: One retry, with the validation error appended. A second one costs money and
#: almost never helps: a model that cannot fill the schema twice will not fill
#: it on the third attempt either.
SCHEMA_RETRIES = 1

logger = log.get_logger(__name__)


class LLMTemporaryError(TemporaryError):
    """The gateway was unreachable, overloaded or rate-limited."""


class LLMError(Exception):
    """The gateway refused the request, or the model would not fill the schema."""


@dataclass(frozen=True)
class Completion:
    """One answer, with what it cost to get it."""

    result: BaseModel
    model: str
    tokens_in: int
    tokens_out: int
    duration_ms: int


class LLMGateway(Protocol):
    """The one thing the application asks of a model."""

    def complete_json(
        self, *, model: str, system: str, user: str, schema: type[BaseModel], max_tokens: int
    ) -> Completion:
        """Return an instance of ``schema``, produced by ``model``."""
        ...


class BifrostGateway:
    """Talks OpenAI-compatible JSON to whatever sits behind the gateway URL."""

    def __init__(
        self, base_url: str, api_key: str, timeout: int, client: httpx.Client | None = None
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._http = client or httpx.Client(timeout=timeout)

    def complete_json(
        self, *, model: str, system: str, user: str, schema: type[BaseModel], max_tokens: int
    ) -> Completion:
        """Ask for a structured answer and validate it before returning."""
        started = time.monotonic()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

        for attempt in range(SCHEMA_RETRIES + 1):
            payload = self._post(model, messages, schema, max_tokens)
            content = payload["choices"][0]["message"]["content"]
            try:
                result = schema.model_validate_json(content)
            except ValidationError as error:
                if attempt == SCHEMA_RETRIES:
                    raise LLMError(f"the model would not fill the schema: {error}") from error
                # Hand the model its own mistake; that is usually enough.
                messages += [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"That did not match the schema: {error}. Try again.",
                    },
                ]
                continue

            usage = payload.get("usage", {})
            return Completion(
                result=result,
                model=payload.get("model", model),
                # Omitted when zero, which is not the same as missing.
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                duration_ms=round((time.monotonic() - started) * 1000),
            )
        raise AssertionError("unreachable")

    def _post(
        self, model: str, messages: list[dict], schema: type[BaseModel], max_tokens: int
    ) -> dict:
        """Perform one call and separate "try later" from "this will not work"."""
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            },
        }
        try:
            response = self._http.post(
                f"{self._base_url}{COMPLETIONS_PATH}",
                json=body,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
        except httpx.HTTPError as error:
            raise LLMTemporaryError(str(error)) from error

        if response.is_success:
            return response.json()
        if response.status_code == 429 or response.status_code >= 500:
            raise LLMTemporaryError(f"gateway: HTTP {response.status_code}")
        raise LLMError(f"gateway: HTTP {response.status_code} {response.text[:200]}")


# --- Ledger and cap ---------------------------------------------------------


def cost_cents(model: str, tokens_in: int, tokens_out: int, settings: Settings) -> Decimal:
    """Work out what one call cost, in cents.

    Every configured model is guaranteed to have a price: start-up refuses a
    configuration where one does not, precisely so that this cannot silently
    return zero and let an unbudgeted model past the cap.
    """
    price = settings.llm.prices_per_million_tokens[model]
    per_million = Decimal(10**6)
    return (
        Decimal(tokens_in) * Decimal(str(price.input)) / per_million
        + Decimal(tokens_out) * Decimal(str(price.output)) / per_million
    ) * 100


def day_start(now: datetime, settings: Settings) -> datetime:
    """Midnight of ``now`` in the product's timezone.

    The cap is a *daily* budget, and "daily" has to mean the same thing in the
    worker and in ``cli status``, or the two disagree about who spent what.
    """
    local = now.astimezone(ZoneInfo(settings.product.timezone))
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def spent_today(session, creator_id: int, now: datetime, settings: Settings) -> Decimal:
    """Return what this creator's calls have cost since local midnight."""
    total = session.scalar(
        select(func.coalesce(func.sum(LLMCall.cost_cents), 0)).where(
            LLMCall.creator_id == creator_id, LLMCall.created_at >= day_start(now, settings)
        )
    )
    return Decimal(total)


def assert_under_cap(session, creator_id: int, now: datetime, settings: Settings) -> None:
    """Refuse to spend more today than the configuration allows.

    Raises
    ------
    CostCapExceeded
        The budget is used up. The row waits for the reset rather than failing.
    """
    spent = spent_today(session, creator_id, now, settings)
    if spent >= settings.llm.daily_cost_cap_cents:
        logger.warning(
            log.LLM_COST_CAP_HIT,
            creator_id=creator_id,
            spent_cents=float(spent),
            cap_cents=settings.llm.daily_cost_cap_cents,
        )
        raise CostCapExceeded(f"{spent:.2f} of {settings.llm.daily_cost_cap_cents} cents used")


def record_call(
    *,
    purpose: str,
    model: str,
    prompt_version: str,
    creator_id: int | None,
    appearance_id: int | None,
    settings: Settings,
    completion: Completion | None = None,
    error: Exception | None = None,
) -> None:
    """Write one line into the cost ledger, in a session of its own.

    The separate session is the whole point. A step that pays for a summary and
    then fails on the next write would otherwise roll back the record of what it
    spent — and ten retries would re-pay against a ledger that never grew,
    defeating the one mechanism that exists to stop exactly that.
    """
    tokens_in = completion.tokens_in if completion else 0
    tokens_out = completion.tokens_out if completion else 0
    used_model = completion.model if completion else model
    cost = cost_cents(model, tokens_in, tokens_out, settings)

    with session_scope() as session:
        session.add(
            LLMCall(
                creator_id=creator_id,
                appearance_id=appearance_id,
                purpose=purpose,
                model=used_model,
                prompt_version=prompt_version,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_cents=cost,
                duration_ms=completion.duration_ms if completion else 0,
                ok=error is None,
            )
        )
    logger.info(
        log.LLM_CALL,
        purpose=purpose,
        model=used_model,
        prompt_version=prompt_version,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_cents=float(cost),
        duration_ms=completion.duration_ms if completion else 0,
        ok=error is None,
        error=str(error) if error else None,
    )
