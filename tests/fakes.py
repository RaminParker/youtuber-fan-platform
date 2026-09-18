"""Stand-ins for the outside world.

They duck-type the real classes rather than implementing a Protocol: the
Protocol exists for the second real implementation, not for the tests. Nothing
in this suite patches an internal — everything enters through ``set_services``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from datetime import UTC, datetime

from app.delivery.render import OutgoingEmail
from app.errors import TemporaryError
from app.services import Services
from app.sources.base import Comment, ContentItem, SourceProfile

__all__ = ["Comment"]  # re-exported so tests can build one without a second import
from app.transcripts.base import TranscriptProvider


def services(
    *,
    youtube: object | None = None,
    transcripts: list[TranscriptProvider] | None = None,
    email: object | None = None,
    youtube_connection: object | None = None,
    llm: object | None = None,
) -> Services:
    """Build a service container, defaulting everything a test does not care about."""
    return Services(
        youtube=youtube or FakeYouTubeConnector(),
        transcripts=transcripts if transcripts is not None else [],
        email=email or FakeEmailClient(),
        youtube_connection=youtube_connection or FakeYouTubeConnection(),
        llm=llm or FakeLLMGateway(),
    )


class FakeLLMGateway:
    """Returns a prepared result, or raises. Records what it was asked."""

    def __init__(
        self,
        results: list | None = None,
        raises: Exception | None = None,
        tokens: tuple[int, int] = (5000, 800),
    ) -> None:
        self.results = list(results or [])
        self.raises = raises
        self.tokens = tokens
        self.calls: list[dict] = []

    def complete_json(self, *, model, system, user, schema, max_tokens):
        from app.analysis.llm import Completion

        self.calls.append({"model": model, "system": system, "user": user, "schema": schema})
        if self.raises is not None:
            raise self.raises
        result = self.results.pop(0) if self.results else _default_for(schema)
        return Completion(
            result=result,
            model=model,
            tokens_in=self.tokens[0],
            tokens_out=self.tokens[1],
            duration_ms=1234,
        )


def _default_for(schema):
    """A plausible, schema-valid answer, so tests need not spell one out."""
    from app.analysis.schemas import KeyPoint, Section, Sentiment, Summary

    if schema is Summary:
        return Summary(
            language="de",
            headline="Warum Verwaltung so langsam ist",
            core_message="Es geht um Zuständigkeiten. Und darum, warum sie niemand ändert.",
            key_points=[
                KeyPoint(text="Zuständigkeiten sind zersplittert.", timestamp_seconds=61),
                KeyPoint(text="Niemand entscheidet allein.", timestamp_seconds=305),
                KeyPoint(text="Reformen scheitern an der Umsetzung.", timestamp_seconds=902),
            ],
            sections=[
                Section(
                    title="Das Problem",
                    key_points=[KeyPoint(text="Zu viele Beteiligte.", timestamp_seconds=150)],
                ),
                Section(
                    title="Was hilft",
                    key_points=[KeyPoint(text="Klare Verantwortung.", timestamp_seconds=1180)],
                ),
            ],
            quote="Es liegt nicht an den Menschen, es liegt an den Zuständigkeiten.",
            quote_timestamp_seconds=740,
        )
    return Sentiment(
        overall="Überwiegend Zustimmung, mit Widerspruch bei den Zahlen.",
        agreed=["Die Analyse der Zuständigkeiten"],
        disagreed=["Die Zahlen aus Minute zwölf"],
        questions=["Wie sieht es in anderen Ländern aus?"],
        comment_count_used=42,
    )


class FakeYouTubeConnection:
    """Completes, or refuses to, exactly as told."""

    def __init__(
        self, channel_id: str = "UCpilot0000000000000000", raises: Exception | None = None
    ):
        self.channel_id = channel_id
        self.raises = raises

    def complete(self, code: str, redirect_uri: str):
        from app.sources.youtube.oauth import ConnectedChannel

        if self.raises is not None:
            raise self.raises
        return ConnectedChannel(channel_id=self.channel_id, refresh_token="refresh-token")


class FakeEmailClient:
    """Collects what would have been sent, so a test can read it back."""

    def __init__(self, fail_with: Exception | None = None) -> None:
        self.sent: list[OutgoingEmail] = []
        self.fail_with = fail_with

    def send(self, mail: OutgoingEmail) -> str:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append(mail)
        return f"fake-{len(self.sent)}"

    @property
    def last(self) -> OutgoingEmail:
        return self.sent[-1]

    def to(self, address: str) -> list[OutgoingEmail]:
        return [mail for mail in self.sent if mail.to == address]


def content_item(
    external_id: str,
    *,
    title: str = "Ein Video",
    published_at: datetime | None = None,
    duration_seconds: int | None = 1200,
    is_public: bool = True,
    is_live_or_upcoming: bool = False,
    comments_disabled: bool = False,
) -> ContentItem:
    """Build a ContentItem, defaulting to "a normal, long enough, public video"."""
    return ContentItem(
        external_id=external_id,
        title=title,
        url=f"https://www.youtube.com/watch?v={external_id}",
        published_at=published_at or datetime(2026, 9, 8, 16, 0, tzinfo=UTC),
        duration_seconds=duration_seconds,
        is_public=is_public,
        is_live_or_upcoming=is_live_or_upcoming,
        comments_disabled=comments_disabled,
    )


class FakeYouTubeConnector:
    """A connector whose world is a dictionary.

    An id that is not in ``items`` behaves exactly like a deleted video: it is
    simply absent from the answer, which is how the pipeline finds out.
    """

    kind = "youtube"

    def __init__(
        self,
        items: list[ContentItem] | None = None,
        comments: list[Comment] | None = None,
        profile: SourceProfile | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self.items = {item.external_id: item for item in (items or [])}
        self.comment_list = comments or []
        self.profile = profile
        self.fail_with = fail_with
        self.calls: list[tuple[str, object]] = []

    def _maybe_fail(self) -> None:
        if self.fail_with is not None:
            raise self.fail_with

    def source_profile(self, source_external_id: str) -> SourceProfile | None:
        self.calls.append(("source_profile", source_external_id))
        self._maybe_fail()
        return self.profile

    def latest_items(self, source_external_id: str, limit: int) -> list[ContentItem]:
        self.calls.append(("latest_items", source_external_id))
        self._maybe_fail()
        return sorted(self.items.values(), key=lambda i: i.published_at, reverse=True)[:limit]

    def item_details(self, external_ids: list[str]) -> list[ContentItem]:
        self.calls.append(("item_details", tuple(external_ids)))
        self._maybe_fail()
        return [self.items[i] for i in external_ids if i in self.items]

    def comments(self, external_id: str, max_count: int) -> list[Comment]:
        self.calls.append(("comments", external_id))
        self._maybe_fail()
        return self.comment_list[:max_count]


class FlakyConnector(FakeYouTubeConnector):
    """Fails temporarily a fixed number of times, then behaves."""

    def __init__(self, failures: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.remaining_failures = failures

    def item_details(self, external_ids: list[str]) -> list[ContentItem]:
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            raise TemporaryError("the network had other plans")
        return super().item_details(external_ids)


class FakeTranscriptProvider:
    """A provider that returns what it was told to, or raises what it was told to."""

    def __init__(self, origin: str, transcript=None, raises: Exception | None = None) -> None:
        self.origin = origin
        self.transcript = transcript
        self.raises = raises
        self.calls = 0

    def fetch(self, source, item, languages):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.transcript


def transcript(origin: str = "youtube_unofficial", language: str = "de", is_generated: bool = True):
    """A short but real transcript."""
    from app.transcripts.base import Segment, Transcript

    return Transcript(
        origin=origin,
        language=language,
        is_generated=is_generated,
        segments=[
            Segment(start=0.0, duration=3.5, text="Guten Abend und willkommen."),
            Segment(start=3.5, duration=5.0, text="Heute geht es um die Verwaltung."),
        ],
    )


#: A webhook secret in the provider's format, for signing test requests.
WEBHOOK_SECRET = "whsec_" + base64.b64encode(b"a-shared-secret-for-webhooks").decode()


def svix_headers(
    body: bytes, secret: str = WEBHOOK_SECRET, *, message_id: str = "msg_1", timestamp: str = ""
) -> dict[str, str]:
    """Sign a body the way the mail provider does: HMAC-SHA256 over ``id.timestamp.body``."""
    timestamp = timestamp or str(int(time.time()))
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{message_id}.{timestamp}.".encode() + body
    digest = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return {"svix-id": message_id, "svix-timestamp": timestamp, "svix-signature": f"v1,{digest}"}
