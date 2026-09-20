"""The gateway: structured output, one retry, and the money it costs."""

import json
from decimal import Decimal

import httpx
import pytest

from app.analysis.llm import BifrostGateway, LLMError, LLMTemporaryError, cost_cents, day_start
from app.analysis.schemas import Sentiment, Summary
from app.config import get_settings
from app.errors import TemporaryError
from tests.fakes import _default_for

VALID = Sentiment(overall="Gemischt.", agreed=[], disagreed=[], questions=[], comment_count_used=3)


def gateway_answering(*bodies) -> tuple[BifrostGateway, list]:
    """A gateway whose transport replies with the given bodies, in order."""
    remaining = list(bodies)
    seen = []

    def handler(request):
        seen.append(request)
        body = remaining.pop(0)
        if isinstance(body, int):
            return httpx.Response(body, json={"error": "nope"})
        return httpx.Response(
            200,
            json={
                "model": "anthropic/claude-sonnet-4-5",
                "choices": [{"message": {"content": body}}],
                "usage": {"prompt_tokens": 5000, "completion_tokens": 800},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return BifrostGateway("http://gateway", "sk-bf-test", 30, client), seen


def ask(gateway):
    return gateway.complete_json(
        model="anthropic/claude-sonnet-4-5",
        system="rules",
        user="data",
        schema=Sentiment,
        max_tokens=1000,
    )


class TestStructuredOutput:
    def test_a_valid_answer_comes_back_as_an_object(self):
        gateway, _ = gateway_answering(VALID.model_dump_json())

        completion = ask(gateway)

        assert isinstance(completion.result, Sentiment)
        assert completion.result.overall == "Gemischt."

    def test_token_counts_are_carried_through(self):
        gateway, _ = gateway_answering(VALID.model_dump_json())

        completion = ask(gateway)

        assert (completion.tokens_in, completion.tokens_out) == (5000, 800)

    def test_a_missing_usage_block_counts_as_zero_not_as_a_crash(self):
        def handler(request):
            return httpx.Response(
                200, json={"choices": [{"message": {"content": VALID.model_dump_json()}}]}
            )

        gateway = BifrostGateway(
            "http://g", "k", 30, httpx.Client(transport=httpx.MockTransport(handler))
        )

        assert ask(gateway).tokens_in == 0

    def test_the_schema_travels_with_the_request(self):
        gateway, seen = gateway_answering(VALID.model_dump_json())

        ask(gateway)

        import json

        body = json.loads(seen[0].content)
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["name"] == "Sentiment"


class TestSchemaRetry:
    def test_a_malformed_answer_is_handed_back_to_the_model_once(self):
        gateway, seen = gateway_answering('{"nonsense": true}', VALID.model_dump_json())

        completion = ask(gateway)

        assert isinstance(completion.result, Sentiment)
        assert len(seen) == 2

    def test_the_second_failure_is_not_retried_again(self):
        # A model that cannot fill the schema twice will not fill it on the
        # third attempt either, and every attempt costs money.
        gateway, seen = gateway_answering('{"a": 1}', '{"b": 2}')

        with pytest.raises(LLMError):
            ask(gateway)

        assert len(seen) == 2


class TestErrors:
    @pytest.mark.parametrize("status", [429, 500, 502, 503])
    def test_overload_is_worth_retrying(self, status):
        gateway, _ = gateway_answering(status)

        with pytest.raises(LLMTemporaryError):
            ask(gateway)

    def test_a_refused_request_is_permanent(self):
        gateway, _ = gateway_answering(400)

        with pytest.raises(LLMError):
            ask(gateway)

    def test_a_network_failure_is_worth_retrying(self):
        def explode(request):
            raise httpx.ConnectError("gateway is down")

        gateway = BifrostGateway(
            "http://g", "k", 30, httpx.Client(transport=httpx.MockTransport(explode))
        )

        with pytest.raises(LLMTemporaryError):
            ask(gateway)

    def test_temporary_means_what_the_worker_catches(self):
        assert issubclass(LLMTemporaryError, TemporaryError)


class TestCost:
    def test_it_follows_the_configured_prices(self):
        settings = get_settings()

        # 5000 in at 3.00/M = 0.015, 800 out at 15.00/M = 0.012 -> 0.027 -> 2.7 cents
        cost = cost_cents("anthropic/claude-sonnet-4-5", 5_000, 800, settings)

        assert cost == Decimal("2.7")

    def test_a_free_call_costs_nothing(self):
        assert cost_cents("anthropic/claude-sonnet-4-5", 0, 0, get_settings()) == 0

    def test_it_is_exact_not_floating(self):
        # Money in floats is how ledgers stop adding up.
        assert isinstance(cost_cents("anthropic/claude-sonnet-4-5", 1, 1, get_settings()), Decimal)


class TestDayBoundary:
    def test_the_day_starts_at_local_midnight(self):
        from datetime import UTC, datetime

        settings = get_settings()
        # 00:30 Berlin on 12 September is 22:30 UTC on the 11th.
        start = day_start(datetime(2026, 9, 11, 22, 30, tzinfo=UTC), settings)

        assert (start.year, start.month, start.day) == (2026, 9, 12)
        assert (start.hour, start.minute) == (0, 0)


def objects_in(schema: dict):
    """Every object node of a JSON schema, including the ones under $defs."""
    if isinstance(schema, dict):
        if schema.get("type") == "object":
            yield schema
        for value in schema.values():
            yield from objects_in(value)
    elif isinstance(schema, list):
        for item in schema:
            yield from objects_in(item)


class TestTheSchemaTheProviderAccepts:
    """Found live on 2026-09-19: the provider refuses a strict schema whose
    objects do not say ``additionalProperties: false`` — every summary failed."""

    @pytest.mark.parametrize("model", [Summary, Sentiment])
    def test_every_object_forbids_additional_properties(self, model):
        gateway, seen = gateway_answering(_default_for(model).model_dump_json())

        gateway.complete_json(
            model="anthropic/claude-sonnet-4-5", system="s", user="u", schema=model, max_tokens=10
        )

        schema = json.loads(seen[0].content)["response_format"]["json_schema"]["schema"]
        objects = list(objects_in(schema))
        assert len(objects) > 1 if model is Summary else objects
        assert all(node.get("additionalProperties") is False for node in objects)
