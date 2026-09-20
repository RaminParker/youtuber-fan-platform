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
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import ClassVar, Protocol
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select

from app import log
from app.config import Settings
from app.db.engine import session_scope
from app.db.models import LLMCall
from app.errors import CostCapExceeded, NeedsOperator, TemporaryError

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
    #: Part of ``tokens_in`` that the provider served from, or wrote to, its
    #: cache. Billed at their own factors, so they are kept apart.
    tokens_cached: int = 0
    tokens_cache_write: int = 0


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
            details = usage.get("prompt_tokens_details") or {}
            return Completion(
                result=result,
                model=payload.get("model", model),
                # Omitted when zero, which is not the same as missing.
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                tokens_cached=details.get("cached_tokens", 0),
                tokens_cache_write=details.get("cache_write_tokens", 0),
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
        _raise_if_operator(response, model)
        raise LLMError(f"gateway: HTTP {response.status_code} {response.text[:200]}")


#: What the gateway or the provider says when a key or the account is the
#: problem — words seen in real answers, lower-cased. A 401/403 always is.
_ACCOUNT_TROUBLE = ("no keys found", "api key", "api-key", "credit balance", "workspace", "billing")


#: Where a model is named. Changing it means these three places, together.
MODEL_SETTINGS = (
    "config/settings.toml [llm] model_summary/model_sentiment and its "
    "[llm.prices_per_million_tokens] entry, plus allowed_models in config/bifrost.json"
)


def _raise_if_operator(response: httpx.Response, model: str) -> None:
    """Turn a refused key or an empty account into a message that says what to fix.

    Two keys are involved and either can be wrong: ``LLM_GATEWAY_KEY`` between
    the app and the gateway, ``ANTHROPIC_API_KEY`` between the gateway and the
    provider. The provider's own words are passed on, because they are usually
    the fastest way to the cause.
    """
    said = _upstream_message(response)
    names_a_model = said.startswith("model:") or "model" in said.lower()
    if response.status_code == 404 and not names_a_model:
        # The gateway itself is not where we think it is; nothing about the
        # model would explain this, and pointing at it wastes the operator's
        # first guess.
        raise NeedsOperator(
            "LLM gateway",
            f"the gateway refused the request at {COMPLETIONS_PATH} ({said})",
            "check LLM_GATEWAY_URL and that the gateway is running; if the address is "
            "right, the model may be missing from the gateway — `uv run app gateway-config` "
            "writes the configured models into config/bifrost.json",
        )
    if response.status_code == 404 or said.startswith("model:"):
        raise NeedsOperator(
            "LLM gateway",
            f"model {model} is not available at the provider ({said})",
            f"switch to a model the provider still serves in {MODEL_SETTINGS}",
        )
    if "model_blocked" in response.text or "is not allowed for virtual key" in said:
        raise NeedsOperator(
            "LLM gateway",
            f"model {model} is not allowed by the gateway ({said})",
            f"add it to allowed_models in config/bifrost.json and recreate the gateway; "
            f"a model is named in {MODEL_SETTINGS}",
        )
    if response.status_code in (401, 403):
        raise NeedsOperator(
            "LLM gateway",
            f"key rejected (HTTP {response.status_code}): {said}",
            "check LLM_GATEWAY_KEY (the same value in app and gateway) and ANTHROPIC_API_KEY "
            "(the gateway's key for the provider)",
        )
    if response.status_code in (400, 402) and any(w in said.lower() for w in _ACCOUNT_TROUBLE):
        raise NeedsOperator(
            "LLM gateway",
            f"the provider account cannot serve the request: {said}",
            "check ANTHROPIC_API_KEY (valid, scoped to a workspace, allowed for the model) and "
            "the account's credit; the gateway's start log names the cause (`list-models "
            "failed`); recreate the gateway after a change",
        )


def _upstream_message(response: httpx.Response) -> str:
    """Return the error text of a gateway answer, wherever in the body it sits."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error.get("error") or error)[:300]
    return str(error or body)[:300]


# --- Ledger and cap ---------------------------------------------------------


#: What the provider charges for input it served from its cache, and for
#: writing an entry (five-minute lifetime). Checked 2026-09-20 against the
#: provider's caching documentation. Ignoring these makes the ledger wrong by
#: a factor the day caching is switched on.
#:
#: Measured against the live gateway the same day: a ~10k-token prompt sent
#: twice with a cache breakpoint reported `prompt_tokens: 10155` both times —
#: once with `cache_write_tokens: 10144`, once with `cached_tokens: 10144`. The
#: cached part is therefore *inside* `prompt_tokens`, which is what
#: `Priced.cost_cents` relies on (tests/unit/test_llm_cost.py).
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25

#: How old a price may be before the operator is told to check it. A quarter:
#: long enough not to nag, short enough that a price change cannot quietly
#: outlive a pricing decision made on it.
PRICE_MAX_AGE = timedelta(days=90)


@dataclass(frozen=True)
class Priced:
    """The price that was applied to one call, and where it came from."""

    #: Marks a call whose model nobody configured a price for.
    UNKNOWN: ClassVar[str] = "unknown"

    input: float
    output: float
    source: str
    #: True when the answering model could not be matched and the price of the
    #: model we asked for was used instead. The number is honest arithmetic on
    #: a price that may belong to something else — which the ledger says.
    assumed: bool = False

    @property
    def is_known(self) -> bool:
        """Whether a real price was found, or the call is uncosted."""
        return self.source != self.UNKNOWN

    def require_known_error(self) -> NeedsOperator:
        """Build the message an uncosted call has to leave behind."""
        if self.is_known:
            raise AssertionError("a known price has nothing to report")
        return NeedsOperator(
            "LLM cost ledger",
            f"no price configured for the model that answered ({self.source})",
            "add it to [llm.prices_per_million_tokens] in config/settings.toml, with "
            "source and checked_on; until then the call is booked at zero and the "
            "daily cap cannot see it",
        )

    def cost_cents(
        self,
        tokens_in: int,
        tokens_out: int,
        tokens_cached: int = 0,
        tokens_cache_write: int = 0,
    ) -> Decimal:
        """Work out what one call cost, in cents.

        ``tokens_in`` is what the provider reports as input and already counts
        the cached and newly written tokens; they are billed at their own
        factors, so they are taken out of the full-price part rather than paid
        twice.
        """
        full = max(0, tokens_in - tokens_cached - tokens_cache_write)
        per_million = Decimal(10**6)
        billable_in = (
            Decimal(full)
            + Decimal(tokens_cached) * Decimal(str(CACHE_READ_FACTOR))
            + Decimal(tokens_cache_write) * Decimal(str(CACHE_WRITE_FACTOR))
        )
        return (
            billable_in * Decimal(str(self.input)) / per_million
            + Decimal(tokens_out) * Decimal(str(self.output)) / per_million
        ) * 100


def price_of(model: str, settings: Settings) -> Priced:
    """Find the price for the model that actually answered.

    The configuration names a model family (``anthropic/claude-sonnet-4-5``);
    the gateway answers with the dated snapshot it routed to
    (``claude-sonnet-4-5-20250929``), sometimes without the provider prefix.
    An exact entry wins; otherwise the longest family whose name the answer
    carries. Nothing is invented: a model nobody priced comes back as
    ``UNKNOWN`` and the caller makes noise about it.
    """
    prices = settings.llm.prices_per_million_tokens
    if (exact := prices.get(model)) is not None:
        return Priced(exact.input, exact.output, model)

    # Longest family first, measured on the model name rather than the whole
    # key: "claude-sonnet-4-5" must win over "claude-sonnet" for a dated
    # snapshot of 4.5, whatever provider prefixes the two keys carry.
    bare = model.split("/")[-1]
    families = sorted(prices, key=lambda name: len(name.split("/")[-1]), reverse=True)
    for name in families:
        # Only in this direction: an answer that is *shorter* than a configured
        # family (a bare alias) tells us nothing about which one it is, and
        # guessing would book one model at another's price.
        if bare.startswith(name.split("/")[-1]):
            return Priced(prices[name].input, prices[name].output, name)
    return Priced(0.0, 0.0, Priced.UNKNOWN)


def price_for_booking(asked: str, answered: str, settings: Settings) -> Priced:
    """Return the price to book one call at, and never zero.

    The answering model is priced when it can be matched. When it cannot — a
    gateway that starts routing somewhere new, an alias nobody configured —
    the model we *asked* for is used, because start-up guarantees it has a
    price. Booking zero instead would not just be a missing number: the daily
    cap sums the ledger, so a zero switches off the one guard that stops a
    runaway loop from spending all day.
    """
    priced = price_of(answered, settings)
    if priced.is_known:
        return priced
    fallback = price_of(asked, settings)
    if not fallback.is_known:
        return priced  # nothing to fall back on; the caller reports it
    return Priced(fallback.input, fallback.output, fallback.source, assumed=True)


def stale_prices(settings: Settings, today: date) -> dict[str, date]:
    """Return every price that has not been checked within ``PRICE_MAX_AGE``."""
    return {
        name: price.checked_on
        for name, price in settings.llm.prices_per_million_tokens.items()
        if today - price.checked_on > PRICE_MAX_AGE
    }


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
    tokens_cached = completion.tokens_cached if completion else 0
    tokens_cache_write = completion.tokens_cache_write if completion else 0
    used_model = completion.model if completion else model
    # Priced by the model that answered, not by the one we asked for: the
    # gateway may route to a dated snapshot, and a row must never carry a
    # precise model name next to a price that belongs to something else.
    priced = price_for_booking(model, used_model, settings)
    if priced.assumed or not priced.is_known:
        log.report_operator_action(
            Priced(0.0, 0.0, used_model).require_known_error(), model=used_model
        )
    cost = priced.cost_cents(tokens_in, tokens_out, tokens_cached, tokens_cache_write)

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
                tokens_cached=tokens_cached,
                tokens_cache_write=tokens_cache_write,
                price_input=priced.input,
                price_output=priced.output,
                price_source=priced.source,
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
