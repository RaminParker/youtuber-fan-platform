"""Unguessable URL tokens. One place, so raising the entropy is one edit.

Every token the product hands out — the summary page's `view_token`, a
subscription's confirm and unsubscribe tokens, a mailing's stop token, a magic
link — comes from here. They differ in lifetime, not in strength.
"""

from __future__ import annotations

import secrets

#: 256 bits. `token_urlsafe(32)` renders them as 43 characters, which is what
#: `db.models.TOKEN_LENGTH` leaves room for.
TOKEN_BYTES = 32


def new_token() -> str:
    """Generate one URL-safe token."""
    return secrets.token_urlsafe(TOKEN_BYTES)
