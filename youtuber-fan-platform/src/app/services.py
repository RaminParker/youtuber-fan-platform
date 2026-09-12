"""The external services, built once per process, replaced wholesale in tests.

This is the entire dependency-injection story. Steps and routes call
:func:`get_services`; the only override is :func:`set_services`, and only the
test suite uses it. Nothing else is patched anywhere.

``# ponytail: a process-global override; switch to explicit injection if a
second process model ever appears.``
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.analysis.llm import BifrostGateway, LLMGateway
from app.config import Settings, get_settings
from app.delivery.email_client import ResendClient
from app.sources.base import SourceConnector
from app.sources.youtube.connector import YouTubeConnector
from app.sources.youtube.data_api import YouTubeDataApi
from app.sources.youtube.oauth import GoogleOAuth, YouTubeConnection
from app.transcripts.base import TranscriptProvider
from app.transcripts.youtube_official import OfficialCaptions
from app.transcripts.youtube_unofficial import UnofficialCaptions

_services: Services | None = None


@dataclass(frozen=True)
class Services:
    """Everything that talks to the outside world.

    The connector is held, never the raw API client: a test fake replaces the
    whole connector and therefore never has to imitate JSON.
    """

    youtube: SourceConnector
    transcripts: list[TranscriptProvider]
    email: ResendClient
    llm: LLMGateway
    youtube_connection: YouTubeConnection


def build_services(settings: Settings) -> Services:
    """Construct the real clients from the configuration."""
    http = httpx.Client(timeout=30)
    api = YouTubeDataApi(settings.secrets.youtube_api_key, http)
    oauth = GoogleOAuth(
        settings.secrets.google_oauth_client_id, settings.secrets.google_oauth_client_secret, http
    )
    return Services(
        youtube=YouTubeConnector(api),
        email=ResendClient(settings.secrets.resend_api_key, http),
        llm=BifrostGateway(
            settings.secrets.llm_gateway_url,
            settings.secrets.llm_gateway_key,
            settings.llm.timeout_seconds,
        ),
        youtube_connection=YouTubeConnection(oauth, api),
        # Order matters: the official provider is the legally clean one, so it
        # is asked first whenever the creator has connected YouTube.
        transcripts=[
            OfficialCaptions(api, oauth, settings.secrets.token_encryption_keys),
            UnofficialCaptions(
                settings.secrets.transcript_proxy_username,
                settings.secrets.transcript_proxy_password,
            ),
        ],
    )


def get_services() -> Services:
    """Return the process-wide services, built on first use."""
    global _services
    if _services is None:
        _services = build_services(get_settings())
    return _services


def set_services(services: Services | None) -> None:
    """Replace the services, or drop them so the next call rebuilds. Tests only."""
    global _services
    _services = services
