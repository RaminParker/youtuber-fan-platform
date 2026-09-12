"""Resolving the file defaults against one creator's overrides.

Manifest §7.1: what varies per channel lives in the database and overrides the
central file. This module is the only place that resolves the two, so no code
path can accidentally read a file default while a creator value exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.db.models import Creator


@dataclass(frozen=True)
class EffectiveSettings:
    """What actually applies to one creator, defaults already resolved."""

    send_delay_hours: int
    min_duration_seconds: int
    email_variant: str


def effective_settings(creator: Creator, settings: Settings) -> EffectiveSettings:
    """Resolve a creator's nullable overrides against the configured defaults.

    A ``None`` column means "use the file default"; that is the whole rule, and
    it lives here so that the settings form and the pipeline cannot disagree.
    """
    return EffectiveSettings(
        send_delay_hours=_or_default(
            creator.send_delay_hours, settings.schedule.default_delay_hours
        ),
        min_duration_seconds=_or_default(
            creator.min_duration_seconds, settings.content.min_duration_seconds
        ),
        email_variant=_or_default(creator.email_variant, settings.email.default_variant),
    )


def _or_default[T](override: T | None, default: T) -> T:
    """Return the override when one is set, the default otherwise."""
    return default if override is None else override
