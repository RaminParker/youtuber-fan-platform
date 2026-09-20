"""Configuration: one TOML file, secrets from the environment, validated at start-up.

Precedence, highest first: values passed to ``Settings(...)``, environment
variables, ``.env``, ``config/settings.toml``, field defaults. TOML tables are
overridable with a double underscore, e.g. ``LOGGING__JSON=true``.
"""

from __future__ import annotations

import functools
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_FILE = REPO_ROOT / "config" / "settings.toml"

_PSYCOPG_SCHEME = "postgresql+psycopg://"
_BARE_SCHEMES = ("postgresql://", "postgres://")


class ProductSettings(BaseModel):
    """Identity of the product. The name lives here and nowhere else."""

    name: str
    domain: str
    timezone: str


class ScheduleSettings(BaseModel):
    """When a summary mail is sent, previewed and enriched with sentiment."""

    default_delay_hours: int
    min_delay_hours: int
    max_delay_hours: int
    sentiment_lead_hours: int
    stop_window_minutes: int
    postpone_hours: int


class ContentSettings(BaseModel):
    """Which items are worth processing, and how much text the summariser takes."""

    min_duration_seconds: int
    backfill_count: int
    max_transcript_chars: int
    transcript_languages: list[str]


class CommentSettings(BaseModel):
    """Heuristic filter applied before comments reach the LLM (manifest §3.1)."""

    max_count: int
    min_words: int
    drop_with_links: bool
    drop_channel_owner: bool


class ModelPrice(BaseModel):
    """Price of one model in currency units per million tokens.

    ``source`` and ``checked_on`` are not decoration: a customer's price is
    calculated from these numbers, and nobody can trust a figure whose origin
    and age are unknown. The provider's invoice remains the authority; this is
    an estimate that has to be able to say how old it is.
    """

    input: float
    output: float
    source: str
    checked_on: date


class LLMSettings(BaseModel):
    """Models, limits and the daily cost cap (manifest §8, §7.9)."""

    model_summary: str
    model_sentiment: str
    max_output_tokens: int
    timeout_seconds: int
    daily_cost_cap_cents: int
    summary_prompt_version: str
    sentiment_prompt_version: str
    #: Where the provider shows what was actually spent. Our ledger is an
    #: estimate; this page is the invoice, and it belongs next to every figure
    #: we print so nobody has to take our arithmetic on faith.
    usage_dashboard: str
    prices_per_million_tokens: dict[str, ModelPrice]

    # "model_" is pydantic's own namespace; our fields are configuration, not models.
    model_config = {"protected_namespaces": ()}

    @model_validator(mode="after")
    def check_every_used_model_has_a_price(self) -> LLMSettings:
        """Fail at start-up when a configured model has no price entry.

        Without this, swapping a model would either fail at the first call or,
        worse, book a cost of zero and silently bypass the daily cap.
        """
        missing = {self.model_summary, self.model_sentiment} - set(self.prices_per_million_tokens)
        if missing:
            raise ValueError(
                f"no price in [llm.prices_per_million_tokens] for: {', '.join(sorted(missing))}"
            )
        return self


class EmailSettings(BaseModel):
    """Mail variants, token lifetimes and the limits on creator-supplied text."""

    variants: list[str]
    default_variant: str
    confirm_token_days: int
    unsubscribed_retention_days: int
    magic_link_minutes: int
    session_hours: int
    max_custom_text_chars: int

    @model_validator(mode="after")
    def check_default_variant_exists(self) -> EmailSettings:
        """Fail at start-up when the default variant is not one of the variants."""
        if self.default_variant not in self.variants:
            raise ValueError(
                f"default_variant {self.default_variant!r} is not in variants {self.variants}"
            )
        return self


class WebSettings(BaseModel):
    """Rate limits. Sign-up is limited per IP *and* per address (§10)."""

    rate_limit_signup: str
    rate_limit_magic_link: str
    rate_limit_contact: str
    confirm_resend_minutes: int
    check_address_dns: bool


class WorkerSettings(BaseModel):
    """How often the worker looks for work."""

    loop_seconds: int
    feed_poll_hours: int


class LoggingSettings(BaseModel):
    """Log level, format and optional local file (§12)."""

    # The TOML key and the env override stay `json` / LOGGING__JSON; the Python
    # attribute is renamed because `json` shadows a BaseModel attribute.
    model_config = {"populate_by_name": True}

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]
    json_format: bool = Field(alias="json")
    file: str


class Secrets(BaseSettings):
    """Secrets and per-environment values, read from the environment only.

    ``.env.example`` is the authority for this list. Only the two values the
    processes need to boot are required; the rest belong to layers that arrive
    in later milestones and are validated where they are used, so that the app
    still starts with an incomplete ``.env``.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    secret_key: str

    base_url: str = ""
    support_email: str = ""
    sender_address: str = ""
    token_encryption_keys: str = ""
    youtube_api_key: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    transcript_proxy_username: str = ""
    transcript_proxy_password: str = ""
    resend_api_key: str = ""
    resend_webhook_secret: str = ""
    llm_gateway_url: str = ""
    llm_gateway_key: str = ""
    sentry_dsn: str = ""

    @field_validator("database_url")
    @classmethod
    def use_the_psycopg_driver(cls, value: str) -> str:
        """Normalise every Postgres URL spelling to the driver we actually use.

        Render injects ``postgresql://`` and shows ``postgres://`` in its
        dashboard; SQLAlchemy needs the driver named explicitly.
        """
        for scheme in _BARE_SCHEMES:
            if value.startswith(scheme):
                return _PSYCOPG_SCHEME + value[len(scheme) :]
        return value


class Settings(BaseSettings):
    """Everything the application can be tuned with."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
        toml_file=SETTINGS_FILE,
    )

    product: ProductSettings
    schedule: ScheduleSettings
    content: ContentSettings
    comments: CommentSettings
    llm: LLMSettings
    email: EmailSettings
    web: WebSettings
    worker: WorkerSettings
    logging: LoggingSettings

    secrets: Secrets = Field(default_factory=lambda: Secrets())  # type: ignore[call-arg]

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Order the sources so that the environment can override the TOML file.

        The pydantic docs' minimal example returns only the TOML source, which
        silently disables every environment override.
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
        )

    @model_validator(mode="after")
    def check_schedule_is_consistent(self) -> Settings:
        """Fail at start-up on a schedule that cannot be honoured."""
        s = self.schedule
        if s.min_delay_hours < 1:
            raise ValueError("schedule.min_delay_hours must be at least 1")
        if not s.min_delay_hours <= s.default_delay_hours <= s.max_delay_hours:
            raise ValueError(
                "schedule.default_delay_hours must lie between min_delay_hours and max_delay_hours"
            )
        if s.stop_window_minutes >= s.sentiment_lead_hours * 60:
            raise ValueError(
                "schedule.stop_window_minutes must be shorter than sentiment_lead_hours, "
                "otherwise the preview would be sent before the sentiment exists"
            )
        return self

    @property
    def base_url(self) -> str:
        """Public base URL for every link in a mail or on a page."""
        return self.secrets.base_url or f"https://{self.product.domain}"

    @property
    def mail_domain(self) -> str:
        """Dedicated sending subdomain (manifest §7.6 deliverability)."""
        return f"mail.{self.product.domain}"

    @property
    def sender_address(self) -> str:
        """Envelope sender for every outgoing mail.

        Overridable because the mail provider refuses every sender on a domain
        it has not verified; until then only its own test sender works.
        """
        return self.secrets.sender_address or f"post@{self.mail_domain}"

    @property
    def support_email(self) -> str:
        """Address a human reads: reply-to fallback and contact-form recipient.

        Overridable because it must point at a real mailbox; the apex domain has
        no MX record until someone sets one up (plan §20).
        """
        return self.secrets.support_email or f"hallo@{self.product.domain}"


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, built once.

    Tests call ``get_settings.cache_clear()`` after changing the environment.
    """
    return Settings()  # type: ignore[call-arg]


def missing_secrets(settings: Settings, needed: dict[str, str]) -> dict[str, str]:
    """Return the needed environment variables that are empty, with what breaks.

    Parameters
    ----------
    needed
        Variable name (as in ``.env``) → what fails without it.
    """
    return {
        name: consequence
        for name, consequence in needed.items()
        if not getattr(settings.secrets, name.lower())
    }
