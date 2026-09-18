"""Captions through the official API, with the creator's own authorisation.

The legally clean path, and the reason the onboarding asks for an OAuth grant at
all. It costs 250 quota units per video — 50 to list the tracks, 200 to download
one — which is why the chain offers it once per row and not once per attempt.
"""

from __future__ import annotations

from app import log
from app.db.models import Source
from app.sources.base import ContentItem
from app.sources.youtube.data_api import CaptionsNotAvailable, YouTubeDataApi
from app.sources.youtube.oauth import GoogleOAuth, GrantRevoked, decrypt_token, encrypt_token
from app.transcripts.base import Transcript, TranscriptUnavailable
from app.transcripts.srt import parse_srt

ORIGIN = "youtube_official"

#: A track the creator wrote beats one the machine guessed.
_UPLOADED = "standard"

logger = log.get_logger(__name__)


def pick_track(tracks: list[dict], languages: list[str]) -> dict | None:
    """Choose the best caption track.

    Preference order: the configured languages, and within a language a track
    the creator uploaded over an automatic one. Falls back to any track at all,
    because a transcript in an unexpected language still beats no transcript.
    """
    for language in languages:
        matching = [t for t in tracks if t.get("snippet", {}).get("language") == language]
        if matching:
            return _prefer_uploaded(matching)
    return _prefer_uploaded(tracks) if tracks else None


def _prefer_uploaded(tracks: list[dict]) -> dict:
    """Return the human-made track if there is one."""
    uploaded = [t for t in tracks if t.get("snippet", {}).get("trackKind") == _UPLOADED]
    return uploaded[0] if uploaded else tracks[0]


class OfficialCaptions:
    """Reads captions as the channel owner."""

    origin = ORIGIN

    def __init__(self, api: YouTubeDataApi, oauth: GoogleOAuth, encryption_keys: str) -> None:
        self._api = api
        self._oauth = oauth
        self._keys = encryption_keys

    def fetch(self, source: Source, item: ContentItem, languages: list[str]) -> Transcript:
        """Return the video's captions.

        Raises
        ------
        TranscriptUnavailable
            No grant, no track, or a track the API refuses to hand over. In each
            case the chain simply moves on to the next provider, in the same run
            — this is not a retry.
        """
        access_token = self._access_token(source)

        try:
            tracks = self._api.captions_list(item.external_id, access_token)
        except CaptionsNotAvailable as error:
            raise TranscriptUnavailable(error.reason) from error

        track = pick_track(tracks, languages)
        if track is None:
            raise TranscriptUnavailable("no_captions")

        try:
            srt = self._api.captions_download(track["id"], access_token)
        except CaptionsNotAvailable as error:
            raise TranscriptUnavailable(error.reason) from error

        snippet = track.get("snippet", {})
        return Transcript(
            origin=ORIGIN,
            language=snippet.get("language", languages[0] if languages else "de"),
            is_generated=snippet.get("trackKind") != _UPLOADED,
            segments=parse_srt(srt),
        )

    def _access_token(self, source: Source) -> str:
        """Turn the stored refresh token into a usable access token.

        Mutates ``source`` on purpose: a rotated refresh token has to be kept or
        the grant is lost, and a revoked one has to be flagged so the creator can
        be asked to reconnect. The step's transaction persists both.
        """
        if not source.oauth_refresh_token_enc or source.oauth_needs_reconsent:
            raise TranscriptUnavailable("no_grant")

        try:
            refresh_token = decrypt_token(source.oauth_refresh_token_enc, self._keys)
            token = self._oauth.refresh_access_token(refresh_token)
        except GrantRevoked as error:
            source.oauth_needs_reconsent = True
            logger.warning(log.OAUTH_REVOKED, source_id=source.id, error=str(error))
            raise TranscriptUnavailable("no_grant") from error

        if token.new_refresh_token:
            source.oauth_refresh_token_enc = encrypt_token(token.new_refresh_token, self._keys)
        return token.access_token
