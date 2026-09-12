"""Google OAuth for the captions scope, and the encryption of what it hands back.

About forty lines of HTTP. ``google-auth-oauthlib`` would add three packages to
build two URLs and post two forms.

Only the refresh token is ever stored, and only encrypted — Google's policy
requires it, and it is the one credential that would let someone read a
creator's captions for as long as the grant lasts. Access tokens live in memory
for the length of one call.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.errors import TemporaryError
from app.sources.youtube.data_api import safe_json

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

#: Captions need the write scope: youtube.readonly cannot download a track.
#: This list must match the consent screen exactly, or Google shows the
#: unverified-app warning to the creator.
SCOPES = ("https://www.googleapis.com/auth/youtube.force-ssl",)

TIMEOUT_SECONDS = 30


class OAuthTemporaryError(TemporaryError):
    """The token endpoint was unreachable or unwell. Try again later."""


class GrantRevoked(Exception):
    """The creator withdrew the grant, or it expired. Only they can fix it."""


@dataclass(frozen=True)
class Grant:
    """What the callback's code was worth: a lasting token and a usable one."""

    refresh_token: str
    access_token: str


@dataclass(frozen=True)
class AccessToken:
    """A short-lived token, plus a replacement refresh token if one was issued."""

    access_token: str
    new_refresh_token: str | None


def authorization_url(client_id: str, redirect_uri: str, state: str) -> str:
    """Build the URL the creator is sent to.

    ``access_type=offline`` with ``prompt=consent`` is what makes Google issue a
    refresh token at all — without the second one, a creator who has granted
    access before gets no refresh token and the grant dies within the hour.
    """
    return f"{AUTHORIZE_URL}?" + urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )


class GoogleOAuth:
    """The two token-endpoint calls."""

    def __init__(
        self, client_id: str, client_secret: str, client: httpx.Client | None = None
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._http = client or httpx.Client(timeout=TIMEOUT_SECONDS)

    def exchange_code(self, code: str, redirect_uri: str) -> Grant:
        """Trade the callback's code for a refresh token and a first access token."""
        payload = self._post(
            {
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            }
        )
        refresh_token = payload.get("refresh_token")
        if not refresh_token:
            # Without prompt=consent Google silently omits it, and the grant
            # would stop working an hour later for no visible reason.
            raise GrantRevoked("no refresh token was issued")
        return Grant(refresh_token=refresh_token, access_token=payload.get("access_token", ""))

    def refresh_access_token(self, refresh_token: str) -> AccessToken:
        """Trade a refresh token for a usable access token."""
        payload = self._post({"refresh_token": refresh_token, "grant_type": "refresh_token"})
        return AccessToken(
            access_token=payload["access_token"],
            # Google occasionally rotates it; losing the new one loses the grant.
            new_refresh_token=payload.get("refresh_token"),
        )

    def _post(self, form: dict[str, str]) -> dict:
        """Post to the token endpoint and separate "broken" from "revoked"."""
        try:
            response = self._http.post(
                TOKEN_URL,
                data={**form, "client_id": self._client_id, "client_secret": self._client_secret},
            )
        except httpx.HTTPError as error:
            raise OAuthTemporaryError(str(error)) from error

        if response.is_success:
            return response.json()

        error = _error_code(response)
        if error == "invalid_grant":
            raise GrantRevoked(error)
        if response.status_code >= 500:
            raise OAuthTemporaryError(f"token endpoint: HTTP {response.status_code}")
        raise OAuthTemporaryError(f"token endpoint: {error or response.status_code}")


def _error_code(response: httpx.Response) -> str:
    """Pull Google's ``error`` field out of a failed token response."""
    return safe_json(response).get("error", "")


def build_cipher(keys: str) -> MultiFernet:
    """Build the cipher from the configured keys.

    Comma-separated, newest first: the first key encrypts, all of them decrypt,
    which is what makes rotating a key a configuration change rather than a
    migration.

    Parameters
    ----------
    keys
        The value of ``TOKEN_ENCRYPTION_KEYS``.
    """
    parts = [key.strip() for key in keys.split(",") if key.strip()]
    if not parts:
        raise ValueError("TOKEN_ENCRYPTION_KEYS is empty; OAuth tokens cannot be stored")
    return MultiFernet([Fernet(key.encode()) for key in parts])


def encrypt_token(token: str, keys: str) -> str:
    """Encrypt a refresh token for storage."""
    return build_cipher(keys).encrypt(token.encode()).decode()


def decrypt_token(stored: str, keys: str) -> str:
    """Decrypt a stored refresh token.

    Raises
    ------
    GrantRevoked
        When no configured key can read it — a rotated-away key is, from the
        creator's side, indistinguishable from a withdrawn grant, and the cure
        is the same: ask them to connect YouTube again.
    """
    try:
        return build_cipher(keys).decrypt(stored.encode()).decode()
    except InvalidToken as error:
        raise GrantRevoked("stored token cannot be decrypted") from error


@dataclass(frozen=True)
class ConnectedChannel:
    """The outcome of a completed grant: whose channel, and the lasting token."""

    channel_id: str
    refresh_token: str


class YouTubeConnection:
    """The whole connect flow behind one method, so the route stays a route.

    It exists to keep the raw Data API client out of the service container: the
    only reason a caller would need it is ``channels.list?mine=true``, and that
    is this class's business.
    """

    def __init__(self, oauth: GoogleOAuth, api) -> None:
        self._oauth = oauth
        self._api = api

    def complete(self, code: str, redirect_uri: str) -> ConnectedChannel:
        """Exchange the callback's code and find out which channel it grants.

        Raises
        ------
        GrantRevoked
            Google issued no refresh token, or the grant is already gone.
        """
        grant = self._oauth.exchange_code(code, redirect_uri)
        channel = self._api.channel_mine(grant.access_token)
        if channel is None:
            raise GrantRevoked("the grant covers no channel")
        return ConnectedChannel(channel_id=channel["id"], refresh_token=grant.refresh_token)
