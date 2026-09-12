"""Signing in by e-mail, and connecting YouTube."""

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db.engine import session_scope
from app.db.models import Creator, Source, SourceKind
from app.services import set_services
from app.sources.youtube.oauth import GrantRevoked, decrypt_token
from app.web.routes.creator import hash_token
from app.web.server import create_app
from tests import fakes
from tests.fakes import FakeEmailClient, FakeYouTubeConnection

pytestmark = pytest.mark.integration

CHANNEL = "UCpilot0000000000000000"
# A throwaway Fernet key; the real ones come from the environment.
KEYS = "4Xk8vQJ7mZp0sT2aB9cD5eF1gH3iJ6kL8mN0oP2qR4s="


@pytest.fixture
def mailer():
    return FakeEmailClient()


@pytest.fixture
def client(committed_database, monkeypatch, mailer, fake_services):
    monkeypatch.setenv("TOKEN_ENCRYPTION_KEYS", KEYS)
    monkeypatch.setenv("BASE_URL", "http://testserver")
    get_settings.cache_clear()
    set_services(fakes.services(email=mailer, youtube_connection=FakeYouTubeConnection(CHANNEL)))

    with session_scope() as session:
        creator = Creator(slug="pilot", name="Pilotkanal", contact_email="pilot@example.org")
        session.add(creator)
        session.flush()
        session.add(Source(creator_id=creator.id, kind=SourceKind.YOUTUBE, external_id=CHANNEL))

    with TestClient(create_app(), follow_redirects=False) as client:
        yield client


def request_link(client, address="pilot@example.org"):
    return client.post("/creator/login", data={"email": address})


def token_from(mailer) -> str:
    return mailer.last.text.split("/creator/login/")[1].split()[0]


class TestRequestingALink:
    def test_a_known_address_gets_a_mail(self, client, mailer):
        request_link(client)

        assert len(mailer.sent) == 1
        assert mailer.last.to == "pilot@example.org"

    def test_an_unknown_address_gets_no_mail(self, client, mailer):
        request_link(client, "stranger@example.org")

        assert mailer.sent == []

    def test_but_the_answer_is_the_same_either_way(self, client, mailer):
        # Otherwise the form tells anyone who asks who is a customer.
        known = request_link(client)
        unknown = request_link(client, "stranger@example.org")

        assert known.status_code == unknown.status_code == 200
        assert known.text == unknown.text

    def test_the_address_is_matched_case_insensitively(self, client, mailer):
        request_link(client, "Pilot@Example.ORG")

        assert len(mailer.sent) == 1

    def test_the_token_is_stored_hashed(self, client, mailer):
        request_link(client)
        token = token_from(mailer)

        with session_scope() as session:
            creator = session.scalar(select(Creator))
            # A leaked backup must not be a set of working login links.
            assert creator.magic_link_token_hash != token
            assert creator.magic_link_token_hash == hash_token(token)


class TestBrakes:
    """Two independent ones, because the first can be circumvented."""

    def test_the_ip_limit_still_answers_429(self, client, mailer):
        limit = int(get_settings().web.rate_limit_magic_link.split("/")[0])

        codes = [request_link(client).status_code for _ in range(limit + 2)]

        assert codes[:limit] == [200] * limit
        assert codes[limit:] == [429, 429]

    def test_only_one_link_is_ever_in_flight(self, client, mailer):
        # A login form that mails on demand is a way to flood an inbox, and the
        # per-IP limit is no limit at all when the address can be forged. A
        # second link would buy nothing anyway: the first one still works.
        for _ in range(3):
            request_link(client)

        assert len(mailer.sent) == 1

    def test_a_new_link_is_issued_once_the_old_one_expires(self, client, mailer):
        request_link(client)
        with session_scope() as session:
            session.scalar(select(Creator)).magic_link_expires_at = datetime.now(UTC) - timedelta(
                seconds=1
            )

        request_link(client)

        assert len(mailer.sent) == 2

    def test_and_after_one_has_been_used(self, client, mailer):
        request_link(client)
        client.post(f"/creator/login/{token_from(mailer)}")

        request_link(client)

        assert len(mailer.sent) == 2


class TestTheFormRevealsNothing:
    def test_a_broken_mail_provider_does_not_become_an_existence_oracle(
        self, client, mailer, fake_services
    ):
        # A 500 for a known address and a 200 for an unknown one tells anyone
        # who asks which addresses are customers.
        set_services(
            fakes.services(
                email=FakeEmailClient(fail_with=RuntimeError("provider down")),
                youtube_connection=FakeYouTubeConnection(CHANNEL),
            )
        )

        known = request_link(client)
        unknown = request_link(client, "stranger@example.org")

        assert known.status_code == 200
        assert known.text == unknown.text


class TestFollowingTheLink:
    def test_opening_it_shows_a_button_and_consumes_nothing(self, client, mailer):
        # A corporate link scanner fetches this before the human does. If GET
        # signed anyone in, the creator's only way in would already be spent.
        request_link(client)
        token = token_from(mailer)

        client.get(f"/creator/login/{token}")
        client.get(f"/creator/login/{token}")

        with session_scope() as session:
            assert session.scalar(select(Creator)).magic_link_token_hash is not None

    def test_the_button_signs_in(self, client, mailer):
        request_link(client)

        response = client.post(f"/creator/login/{token_from(mailer)}")

        assert response.status_code == 303
        assert response.headers["location"] == "/creator/einstellungen"

    def test_the_token_works_only_once(self, client, mailer):
        request_link(client)
        token = token_from(mailer)

        client.post(f"/creator/login/{token}")
        second = client.post(f"/creator/login/{token}")

        assert second.status_code == 200
        assert "gilt nicht mehr" in second.text

    def test_an_expired_token_is_refused(self, client, mailer):
        request_link(client)
        token = token_from(mailer)
        with session_scope() as session:
            session.scalar(select(Creator)).magic_link_expires_at = datetime.now(UTC) - timedelta(
                minutes=1
            )

        response = client.post(f"/creator/login/{token}")

        assert "gilt nicht mehr" in response.text

    def test_an_invented_token_is_refused(self, client):
        assert "gilt nicht mehr" in client.post("/creator/login/not-a-real-token").text


class TestSignedInArea:
    def test_it_is_closed_to_strangers(self, client):
        response = client.get("/creator/youtube/verbinden")

        assert response.status_code == 303
        assert response.headers["location"] == "/creator/login"

    def test_signing_out_ends_the_session(self, client, mailer):
        request_link(client)
        client.post(f"/creator/login/{token_from(mailer)}")

        client.post("/creator/abmelden")

        assert client.get("/creator/youtube/verbinden").status_code == 303


class TestConnectingYouTube:
    @pytest.fixture
    def signed_in(self, client, mailer):
        request_link(client)
        client.post(f"/creator/login/{token_from(mailer)}")
        return client

    def test_it_sends_the_creator_to_google(self, signed_in):
        response = signed_in.get("/creator/youtube/verbinden")

        assert response.status_code == 303
        location = response.headers["location"]
        assert location.startswith("https://accounts.google.com/")
        # Without both of these Google issues no refresh token at all.
        assert "access_type=offline" in location
        assert "prompt=consent" in location

    def test_the_callback_stores_the_grant_encrypted(self, signed_in):
        state = start_connect(signed_in)

        response = signed_in.get(f"/creator/youtube/callback?code=abc&state={state}")

        assert "verbunden" in response.text
        with session_scope() as session:
            source = session.scalar(select(Source))
            assert source.oauth_refresh_token_enc != "refresh-token"
            assert decrypt_token(source.oauth_refresh_token_enc, KEYS) == "refresh-token"
            assert source.oauth_needs_reconsent is False

    def test_a_callback_without_a_matching_state_is_refused(self, signed_in):
        start_connect(signed_in)

        response = signed_in.get("/creator/youtube/callback?code=abc&state=forged")

        assert "nicht von hier" in response.text
        with session_scope() as session:
            assert session.scalar(select(Source)).oauth_refresh_token_enc is None

    def test_the_wrong_channel_is_refused(self, signed_in, fake_services):
        # Otherwise we would read somebody else's captions for as long as the
        # grant lasts.
        set_services(
            fakes.services(youtube_connection=FakeYouTubeConnection("UCsomeoneelse00000000"))
        )
        state = start_connect(signed_in)

        response = signed_in.get(f"/creator/youtube/callback?code=abc&state={state}")

        assert "nicht der Kanal" in response.text
        with session_scope() as session:
            assert session.scalar(select(Source)).oauth_refresh_token_enc is None

    def test_a_creator_without_a_channel_gets_a_page_not_a_500(self, signed_in, committed_database):
        with session_scope() as session:
            session.query(Source).delete()
        state = start_connect(signed_in)

        response = signed_in.get(f"/creator/youtube/callback?code=abc&state={state}")

        assert response.status_code == 200
        assert "kein Kanal hinterlegt" in response.text

    def test_a_refused_grant_says_so(self, signed_in, fake_services):
        set_services(
            fakes.services(youtube_connection=FakeYouTubeConnection(raises=GrantRevoked("nope")))
        )
        state = start_connect(signed_in)

        response = signed_in.get(f"/creator/youtube/callback?code=abc&state={state}")

        assert "nicht erteilt" in response.text


def start_connect(client) -> str:
    """Begin the connect flow and return the state Google would echo back."""
    response = client.get("/creator/youtube/verbinden")
    query = parse_qs(urlparse(response.headers["location"]).query)
    return query["state"][0]
