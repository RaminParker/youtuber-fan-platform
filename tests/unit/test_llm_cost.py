"""What a call cost — a number somebody will price a product on.

Three things have to hold, or the ledger is a guess wearing four decimals: the
price must belong to the model that actually answered, a model nobody priced
must be loud rather than free, and every line must say which price it used, so
a row written last month still means something after a price change.

The authority for the numbers stays the provider's invoice. This ledger is an
estimate, and `README.md` says so.
"""

from datetime import date
from decimal import Decimal
from typing import ClassVar

from app.analysis.llm import (
    CACHE_READ_FACTOR,
    CACHE_WRITE_FACTOR,
    Priced,
    price_for_booking,
    price_of,
)
from app.config import ModelPrice, get_settings

SONNET = "anthropic/claude-sonnet-4-5"


def settings_with(**prices) -> object:
    settings = get_settings().model_copy(deep=True)
    settings.llm.prices_per_million_tokens = {
        name: ModelPrice(input=values[0], output=values[1], source="test", checked_on=date.today())
        for name, values in prices.items()
    }
    return settings


class TestFindingThePrice:
    def test_the_model_that_answered_is_the_one_that_is_priced(self):
        # The gateway answers with a dated id; the configuration names the
        # family. Same model, and it must be recognised as such.
        priced = price_of("claude-sonnet-4-5-20250929", settings_with(**{SONNET: (3.0, 15.0)}))

        assert priced.input == 3.0
        assert priced.source == SONNET

    def test_an_exact_match_wins_over_the_family(self):
        settings = settings_with(
            **{SONNET: (3.0, 15.0), "anthropic/claude-sonnet-4-5-20250929": (9.9, 9.9)}
        )

        priced = price_of("claude-sonnet-4-5-20250929", settings)

        assert priced.input == 9.9

    def test_an_answer_shorter_than_any_family_is_not_guessed(self):
        # "claude-sonnet" could be either configured model; picking one would
        # book Sonnet 5 calls at Sonnet 4.5 prices — 150 % of the truth — and
        # nothing would ever say so.
        settings = settings_with(
            **{
                "anthropic/claude-sonnet-5": (2.0, 10.0),
                "anthropic/claude-sonnet-4-5": (3.0, 15.0),
            }
        )

        assert price_of("claude-sonnet", settings).source == Priced.UNKNOWN

    def test_a_dated_snapshot_still_matches_its_own_family(self):
        settings = settings_with(
            **{
                "anthropic/claude-sonnet-5": (2.0, 10.0),
                "anthropic/claude-sonnet-4-5": (3.0, 15.0),
            }
        )

        assert price_of("claude-sonnet-4-5-20250929", settings).input == 3.0
        assert price_of("claude-sonnet-5", settings).input == 2.0

    def test_a_model_nobody_priced_is_not_free(self):
        priced = price_of("some-model-we-never-configured", settings_with(**{SONNET: (3.0, 15.0)}))

        assert priced.source == Priced.UNKNOWN
        assert priced.input == 0  # nothing is invented …
        # … but the row says so, and the caller logs it for the operator.


class TestWhatItCosts:
    def price(self) -> Priced:
        return Priced(input=3.0, output=15.0, source=SONNET)

    def test_plain_tokens_are_the_list_price(self):
        cost = self.price().cost_cents(tokens_in=1_000_000, tokens_out=0)

        assert cost == Decimal("300")  # $3.00

    def test_output_is_priced_separately(self):
        assert self.price().cost_cents(tokens_in=0, tokens_out=1_000_000) == Decimal("1500")

    def test_a_cached_read_is_a_tenth_and_a_write_costs_a_quarter_more(self):
        # The provider bills cached input differently; ignoring it makes the
        # ledger wrong by a factor, silently, the day caching is switched on.
        million = 1_000_000

        read = self.price().cost_cents(tokens_in=million, tokens_out=0, tokens_cached=million)
        written = self.price().cost_cents(
            tokens_in=million, tokens_out=0, tokens_cache_write=million
        )

        assert read == Decimal("300") * Decimal(str(CACHE_READ_FACTOR))
        assert written == Decimal("300") * Decimal(str(CACHE_WRITE_FACTOR))

    def test_cached_tokens_are_part_of_the_reported_input(self):
        # `prompt_tokens` already counts them, so they must not be paid twice.
        million = 1_000_000
        mixed = self.price().cost_cents(tokens_in=million, tokens_out=0, tokens_cached=million // 2)

        full = Decimal("150")  # half a million at full price
        cached = Decimal("150") * Decimal(str(CACHE_READ_FACTOR))
        assert mixed == full + cached

    def test_an_unknown_price_costs_zero_but_is_marked(self):
        unknown = Priced(input=0.0, output=0.0, source=Priced.UNKNOWN)

        assert unknown.cost_cents(tokens_in=10_000, tokens_out=10_000) == 0
        assert not unknown.is_known


class TestTheNumbersHaveAProvenance:
    def test_every_configured_price_says_where_it_came_from_and_when(self):
        # Without this nobody can tell whether the table was checked last week
        # or last year — and the table is what a customer's price rests on.
        for name, price in get_settings().llm.prices_per_million_tokens.items():
            assert price.source, f"{name} has no source"
            assert isinstance(price.checked_on, date), f"{name} has no check date"

    def test_a_stale_table_is_reported(self):
        from app.analysis.llm import stale_prices

        settings = settings_with(**{SONNET: (3.0, 15.0)})
        settings.llm.prices_per_million_tokens[SONNET].checked_on = date(2020, 1, 1)

        assert SONNET in stale_prices(settings, today=date(2026, 9, 20))

    def test_a_fresh_table_is_not(self):
        settings = settings_with(**{SONNET: (3.0, 15.0)})
        settings.llm.prices_per_million_tokens[SONNET].checked_on = date(2026, 9, 1)

        assert not stale_prices_for(settings)


def stale_prices_for(settings) -> dict:
    from app.analysis.llm import stale_prices

    return stale_prices(settings, today=date(2026, 9, 20))


class TestTheCapStillHolds:
    """Booking zero for an unpriced model would let it run all day: the daily
    cap sums what the ledger says, so a zero is not a missing number — it is a
    wrong one, and the one guard against a runaway loop stops working."""

    def test_an_answer_nobody_priced_is_charged_at_the_price_we_asked_for(self):
        # The configured model always has a price (start-up refuses otherwise),
        # so it is the honest fall-back when the answer cannot be matched.
        settings = settings_with(**{SONNET: (3.0, 15.0)})

        priced = price_for_booking(asked=SONNET, answered="something-unexpected", settings=settings)

        assert priced.input == 3.0
        assert priced.cost_cents(tokens_in=1_000_000, tokens_out=0) == Decimal("300")
        assert priced.source == SONNET

    def test_and_the_row_says_the_price_did_not_belong_to_that_answer(self):
        settings = settings_with(**{SONNET: (3.0, 15.0)})

        priced = price_for_booking(asked=SONNET, answered="something-unexpected", settings=settings)

        assert priced.assumed  # visible in the ledger and in the operator's log

    def test_a_matched_answer_is_not_marked_as_assumed(self):
        settings = settings_with(**{SONNET: (3.0, 15.0)})

        priced = price_for_booking(
            asked=SONNET, answered="claude-sonnet-4-5-20250929", settings=settings
        )

        assert not priced.assumed


class TestTheTruthIsAlwaysLinked:
    """Our ledger is an estimate; the provider's usage page is the invoice.

    Whenever we show a number, the place to check it has to be one click away —
    otherwise somebody prices a product on a figure they cannot verify.
    """

    def test_the_configuration_names_the_providers_usage_page(self):
        assert get_settings().llm.usage_dashboard.startswith("https://")

    def test_the_stale_warning_can_carry_it(self):
        from app.analysis.llm import PRICE_MAX_AGE

        assert PRICE_MAX_AGE.days == 90


class TestNobodyElseSeesWhatItCosts:
    """Costs are the operator's business. A creator must not learn what their
    channel costs us, and a fan must never see a figure at all."""

    def test_no_page_or_mail_mentions_money(self):
        from app.config import REPO_ROOT

        forbidden = ("cost_cents", "price_input", "llm_calls", "Kosten", "cents")
        offenders = {}
        for template in (REPO_ROOT / "src" / "app" / "templates").rglob("*"):
            if template.is_file():
                text = template.read_text(encoding="utf-8")
                hits = [word for word in forbidden if word in text]
                if hits:
                    offenders[template.name] = hits

        assert not offenders, f"cost is operator-only, found {offenders}"


class TestTheCacheNumbersAreReadAsTheProviderMeansThem:
    """Measured against the live gateway on 2026-09-20, not assumed.

    A prompt of ~10k tokens was sent twice with a cache breakpoint. Both
    answers reported `prompt_tokens: 10155` — once with `cache_write_tokens:
    10144`, once with `cached_tokens: 10144`. So the cached part is *inside*
    `prompt_tokens`, which is why the cost function subtracts it before
    charging the rest at full price. Getting this backwards would overcharge
    the ledger by a factor on every cached call.
    """

    WRITE: ClassVar[dict] = {
        "prompt_tokens": 10155,
        "completion_tokens": 4,
        "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 10144},
    }
    READ: ClassVar[dict] = {
        "prompt_tokens": 10155,
        "completion_tokens": 4,
        "prompt_tokens_details": {"cached_tokens": 10144, "cache_write_tokens": 0},
    }

    def cost(self, usage: dict) -> Decimal:
        details = usage["prompt_tokens_details"]
        return Priced(input=3.0, output=15.0, source=SONNET).cost_cents(
            tokens_in=usage["prompt_tokens"],
            tokens_out=usage["completion_tokens"],
            tokens_cached=details["cached_tokens"],
            tokens_cache_write=details["cache_write_tokens"],
        )

    def test_a_cached_read_is_far_cheaper_than_the_same_prompt_uncached(self):
        uncached = Priced(input=3.0, output=15.0, source=SONNET).cost_cents(10_155, 4)

        assert self.cost(self.READ) < uncached / 5

    def test_a_cache_write_costs_more_than_the_same_prompt_uncached(self):
        uncached = Priced(input=3.0, output=15.0, source=SONNET).cost_cents(10_155, 4)

        assert self.cost(self.WRITE) > uncached

    def test_neither_is_charged_twice(self):
        # 10_144 of the 10_155 input tokens came from the cache; only the rest
        # may be billed at the full rate.
        full = Decimal(10_155 - 10_144) * Decimal("3.0") / Decimal(10**6) * 100
        cached = Decimal(10_144) * Decimal("3.0") / Decimal(10**6) * 100
        output = Decimal(4) * Decimal("15.0") / Decimal(10**6) * 100

        assert self.cost(self.READ) == full + cached * Decimal(str(CACHE_READ_FACTOR)) + output
