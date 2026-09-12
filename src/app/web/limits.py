"""The rate limiter, in one place so routes can decorate themselves.

In-memory storage, deliberately: there is one web process, and a limit that
forgets itself on deploy costs nothing. A shared store becomes interesting when
a second process does.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import get_settings

#: Limits are read per request, not at import: the value lives in settings.toml
#: and must not be frozen into the module at start-up.
limiter = Limiter(key_func=get_remote_address)


def signup_limit() -> str:
    """Per-IP limit for the fan sign-up form."""
    return get_settings().web.rate_limit_signup


def magic_link_limit() -> str:
    """Per-IP limit for requesting a sign-in link."""
    return get_settings().web.rate_limit_magic_link


def contact_limit() -> str:
    """Per-IP limit for the contact form."""
    return get_settings().web.rate_limit_contact
