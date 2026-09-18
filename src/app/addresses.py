"""E-mail addresses: what counts as one, and what counts as the same one.

Every address is stored lower-cased, so the unique constraint on
``subscribers.email`` is the identity rule. Forms, the webhook and the CLI all
go through here, so that "Fan@Example.org" never becomes a second person.

Validation is strict on purpose. Every spelling that reaches the mail provider
but is not a plain ``local@domain`` — a display name, a quoted local part, a
trailing dot — would be a second row for the same mailbox, and with it a way
around the per-address brake and the complaint block.
"""

from __future__ import annotations

import functools
from typing import Any

import email_validator

#: A resolver that has not answered in this time is treated as "unknown", and
#: the address passes: our DNS having a bad minute must not lock fans out.
DNS_TIMEOUT_SECONDS = 3


class InvalidAddress(ValueError):
    """The text is not an address we can send to."""


def canonical(address: str) -> str:
    """Return the stored spelling of an address: trimmed and lower-cased.

    ``# ponytail: lower-cases the local part too, which RFC 5321 leaves to the
    receiving server; no real provider distinguishes case, so one person never
    becomes two rows.``
    """
    return address.strip().lower()


def validate(raw: str, *, check_dns: bool, resolver: Any = None) -> str:
    """Check that an address can receive mail and return its stored spelling.

    Parameters
    ----------
    raw
        What the person typed.
    check_dns
        Also ask DNS whether the domain accepts mail (MX, or the A/AAAA
        fallback). Catches mistyped domains before their bounce costs the
        sending reputation every creator shares.
    resolver
        For tests: answers DNS queries instead of the network.

    Raises
    ------
    InvalidAddress
        With the library's explanation, for the log — not for the page.
    """
    try:
        result = email_validator.validate_email(
            raw.strip(),
            allow_smtputf8=False,
            allow_quoted_local=False,
            allow_domain_literal=False,
            allow_display_name=False,
            # RFC 5321 length limits (64 for the local part) apply only in strict mode.
            strict=True,
            check_deliverability=check_dns,
            dns_resolver=(resolver or _resolver()) if check_dns else None,
        )
    except email_validator.EmailNotValidError as error:
        raise InvalidAddress(str(error)) from error
    # The ASCII form: an internationalised domain is stored as punycode, the
    # spelling every mail server accepts.
    return canonical(result.ascii_email or result.normalized)


@functools.lru_cache(maxsize=1)
def _resolver() -> Any:
    """One caching resolver per process, so a burst of sign-ups asks DNS once."""
    return email_validator.caching_resolver(timeout=DNS_TIMEOUT_SECONDS)
