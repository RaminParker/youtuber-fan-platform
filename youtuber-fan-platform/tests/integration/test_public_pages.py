"""What a fan and a visitor actually see."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import (
    Analysis,
    AnalysisKind,
    Appearance,
    AppearanceStatus,
    Creator,
    Source,
    SourceKind,
)
from app.web.server import create_app
from tests.fakes import _default_for

pytestmark = pytest.mark.integration

VIEW_TOKEN = "a-view-token-with-enough-entropy"


@pytest.fixture
def pilot(committed_database, monkeypatch):
    from app.analysis.schemas import Sentiment, Summary

    monkeypatch.setenv("BASE_URL", "http://testserver")
    get_settings.cache_clear()

    with session_scope() as session:
        creator = Creator(
            slug="pilot",
            name="Pilotkanal",
            contact_email="pilot@example.org",
            accent_color="#c4452d",
            logo_url="https://yt3.example/p.jpg",
        )
        session.add(creator)
        session.flush()
        source = Source(creator_id=creator.id, kind=SourceKind.YOUTUBE, external_id="UCpilot0")
        session.add(source)
        session.flush()
        appearance = Appearance(
            source_id=source.id,
            external_id="aaaaaaaaaaa",
            title="Warum Verwaltung so langsam ist",
            url="https://www.youtube.com/watch?v=aaaaaaaaaaa",
            published_at=__import__("datetime").datetime(
                2026, 9, 8, tzinfo=__import__("datetime").UTC
            ),
            duration_seconds=1421,
            status=AppearanceStatus.ANALYZED,
            view_token=VIEW_TOKEN,
        )
        session.add(appearance)
        session.flush()
        session.add(
            Analysis(
                appearance_id=appearance.id,
                kind=AnalysisKind.SUMMARY,
                prompt_version="v1",
                model="anthropic/claude-sonnet-4-5",
                content=_default_for(Summary).model_dump(mode="json"),
            )
        )
        session.add(
            Analysis(
                appearance_id=appearance.id,
                kind=AnalysisKind.SENTIMENT,
                prompt_version="v1",
                model="anthropic/claude-sonnet-4-5",
                content=_default_for(Sentiment).model_dump(mode="json"),
            )
        )
        return appearance.id


@pytest.fixture
def client(pilot):
    with TestClient(create_app()) as client:
        yield client


class TestLanding:
    def test_it_shows_the_promise_and_an_example(self, client):
        response = client.get("/")

        assert response.status_code == 200
        assert "Warum Verwaltung so langsam ist" in response.text
        assert "Gespräch vereinbaren" in response.text

    def test_the_legal_pages_exist(self, client):
        assert client.get("/impressum").status_code == 200
        assert client.get("/datenschutz").status_code == 200


class TestSignupPage:
    def test_it_wears_the_creators_branding(self, client):
        response = client.get("/k/pilot")

        assert "Pilotkanal" in response.text
        assert "#c4452d" in response.text
        assert "https://yt3.example/p.jpg" in response.text

    def test_it_asks_for_one_thing(self, client):
        response = client.get("/k/pilot")

        assert response.text.count('type="email"') == 1
        assert response.text.count("<button") == 1

    def test_it_says_a_confirmation_follows(self, client):
        # The double opt-in is a promise, so the page has to make it.
        assert "Bestätigungsmail" in client.get("/k/pilot").text

    def test_an_unknown_creator_is_a_404_page_not_a_stack_trace(self, client):
        response = client.get("/k/nobody")

        assert response.status_code == 404
        assert "Diese Seite gibt es nicht" in response.text


class TestSummaryPage:
    def test_it_renders_the_summary(self, client):
        response = client.get(f"/s/{VIEW_TOKEN}")

        assert response.status_code == 200
        assert "Warum Verwaltung so langsam ist" in response.text
        # The page renders the detailed block: sections, not the compact list.
        assert "Das Problem" in response.text
        assert "Zu viele Beteiligte." in response.text
        assert "Es liegt nicht an den Menschen" in response.text

    def test_it_shows_the_full_text_whatever_the_mail_variant_is(self, client):
        # Manifest §7.6 calls the third variant "Teaser mit Volltext online"; a
        # page mirroring the variant would send a teaser's "weiterlesen" link to
        # another teaser, and the full text would exist nowhere.
        with session_scope() as session:
            session.scalar(select(Creator)).email_variant = "teaser"

        response = client.get(f"/s/{VIEW_TOKEN}")

        assert "Das Problem" in response.text  # a section title: the detailed block
        assert "Weiterlesen" not in response.text

    def test_it_shows_the_community_box_when_there_is_one(self, client):
        assert "Wie die Community reagiert hat" in client.get(f"/s/{VIEW_TOKEN}").text

    def test_it_degrades_cleanly_without_one(self, client):
        with session_scope() as session:
            session.query(Analysis).filter(Analysis.kind == AnalysisKind.SENTIMENT).delete()

        response = client.get(f"/s/{VIEW_TOKEN}")

        assert response.status_code == 200
        assert "Wie die Community reagiert hat" not in response.text

    def test_it_carries_the_platform_notice(self, client):
        assert "kein Ersatz für das Original" in client.get(f"/s/{VIEW_TOKEN}").text

    def test_it_links_the_video_and_the_sign_up_page(self, client):
        response = client.get(f"/s/{VIEW_TOKEN}")

        assert "https://www.youtube.com/watch?v=aaaaaaaaaaa" in response.text
        assert "/k/pilot" in response.text

    def test_it_jumps_into_the_video(self, client):
        response = client.get(f"/s/{VIEW_TOKEN}")

        # Jinja escapes the & in the href, which is correct HTML.
        assert "t=150s" in response.text  # a section's key point
        assert "t=740s" in response.text  # the quote
        assert "02:30" in response.text  # rendered as a clock, not as seconds


class TestVisibility:
    def test_the_page_is_kept_out_of_search(self, client):
        # It must never compete with the video it summarises.
        response = client.get(f"/s/{VIEW_TOKEN}")

        assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
        assert 'name="robots"' in response.text

    def test_a_deleted_video_takes_its_page_with_it(self, client):
        with session_scope() as session:
            session.scalar(select(Appearance)).status = AppearanceStatus.UNAVAILABLE

        response = client.get(f"/s/{VIEW_TOKEN}")

        assert response.status_code == 410
        assert "gibt es nicht mehr" in response.text

    def test_an_invented_token_finds_nothing(self, client):
        assert client.get("/s/not-a-real-token").status_code == 404
