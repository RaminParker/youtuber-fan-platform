"""The configuration must load, let the environment win, and refuse nonsense."""

import pytest
from pydantic import ValidationError

from app.config import (
    EmailSettings,
    LLMSettings,
    ModelPrice,
    ScheduleSettings,
    Settings,
    get_settings,
)


def valid_schedule(**overrides) -> ScheduleSettings:
    defaults = dict(
        default_delay_hours=168,
        min_delay_hours=48,
        max_delay_hours=720,
        sentiment_lead_hours=2,
        stop_window_minutes=60,
        postpone_hours=24,
    )
    return ScheduleSettings(**(defaults | overrides))


class TestLoading:
    def test_the_toml_file_is_the_source_of_the_defaults(self):
        settings = get_settings()
        assert settings.product.name == "Klartext"
        assert settings.email.variants == ["compact", "detailed", "teaser"]
        assert settings.schedule.min_delay_hours == 48

    def test_get_settings_is_cached(self):
        assert get_settings() is get_settings()

    def test_the_environment_overrides_the_toml_file(self, monkeypatch):
        monkeypatch.setenv("LOGGING__JSON", "true")
        monkeypatch.setenv("LOGGING__LEVEL", "WARNING")
        get_settings.cache_clear()

        settings = get_settings()
        assert settings.logging.json_format is True
        assert settings.logging.level == "WARNING"

    def test_a_missing_required_secret_fails(self, monkeypatch):
        monkeypatch.delenv("SECRET_KEY")
        get_settings.cache_clear()

        with pytest.raises(ValidationError, match="secret_key"):
            get_settings()


class TestDatabaseUrl:
    @pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
    def test_both_bare_schemes_get_the_psycopg_driver(self, monkeypatch, scheme):
        monkeypatch.setenv("DATABASE_URL", f"{scheme}://u:p@host:5432/db")
        get_settings.cache_clear()

        assert get_settings().secrets.database_url == "postgresql+psycopg://u:p@host:5432/db"

    def test_an_explicit_driver_is_left_alone(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@host/db")
        get_settings.cache_clear()

        assert get_settings().secrets.database_url == "postgresql+psycopg://u:p@host/db"


class TestDerivedAddresses:
    def test_they_all_follow_from_the_product_domain(self):
        settings = get_settings()
        assert settings.base_url == "https://klartext.tld"
        assert settings.mail_domain == "mail.klartext.tld"
        assert settings.sender_address == "post@mail.klartext.tld"
        assert settings.support_email == "hallo@klartext.tld"

    def test_support_email_can_point_at_a_real_mailbox(self, monkeypatch):
        monkeypatch.setenv("SUPPORT_EMAIL", "owner@example.org")
        get_settings.cache_clear()

        assert get_settings().support_email == "owner@example.org"

    def test_the_sender_can_be_overridden_until_the_domain_is_verified(self, monkeypatch):
        monkeypatch.setenv("SENDER_ADDRESS", "onboarding@resend.dev")
        get_settings.cache_clear()

        assert get_settings().sender_address == "onboarding@resend.dev"

    def test_base_url_can_be_overridden_for_local_development(self, monkeypatch):
        monkeypatch.setenv("BASE_URL", "http://localhost:8000")
        get_settings.cache_clear()

        assert get_settings().base_url == "http://localhost:8000"


class TestStartUpValidation:
    """Every one of these would otherwise fail later, in production, quietly."""

    def test_a_delay_below_the_minimum_is_refused(self):
        with pytest.raises(ValidationError, match="must lie between"):
            Settings(schedule=valid_schedule(default_delay_hours=24))

    def test_a_delay_above_the_maximum_is_refused(self):
        with pytest.raises(ValidationError, match="must lie between"):
            Settings(schedule=valid_schedule(default_delay_hours=1000))

    def test_a_minimum_delay_of_zero_is_refused(self):
        with pytest.raises(ValidationError, match="at least 1"):
            Settings(schedule=valid_schedule(min_delay_hours=0, default_delay_hours=0))

    def test_a_stop_window_longer_than_the_sentiment_lead_is_refused(self):
        # The preview would go out before the sentiment it is supposed to show.
        with pytest.raises(ValidationError, match="stop_window_minutes"):
            Settings(schedule=valid_schedule(sentiment_lead_hours=1, stop_window_minutes=90))

    def test_a_model_without_a_price_is_refused(self):
        # Booking cost 0 would silently bypass the daily cap.
        with pytest.raises(ValidationError, match="no price"):
            LLMSettings(
                model_summary="anthropic/claude-sonnet-4-5",
                model_sentiment="openai/gpt-nonexistent",
                max_output_tokens=4000,
                timeout_seconds=120,
                daily_cost_cap_cents=500,
                summary_prompt_version="v1",
                sentiment_prompt_version="v1",
                prices_per_million_tokens={
                    "anthropic/claude-sonnet-4-5": ModelPrice(input=3.0, output=15.0)
                },
            )

    def test_a_default_variant_that_does_not_exist_is_refused(self):
        with pytest.raises(ValidationError, match="not in variants"):
            EmailSettings(
                variants=["compact", "detailed"],
                default_variant="teaser",
                confirm_token_days=7,
                unsubscribed_retention_days=30,
                magic_link_minutes=15,
                session_hours=24,
                max_custom_text_chars=300,
            )


class TestMissingSecrets:
    def test_only_empty_ones_are_reported_with_what_breaks(self, monkeypatch):
        from app.config import get_settings, missing_secrets

        monkeypatch.setenv("RESEND_API_KEY", "re_set")
        monkeypatch.setenv("YOUTUBE_API_KEY", "")
        get_settings.cache_clear()
        needed = {"RESEND_API_KEY": "no mail", "YOUTUBE_API_KEY": "no videos"}

        assert missing_secrets(get_settings(), needed) == {"YOUTUBE_API_KEY": "no videos"}
