"""The web process must come up and tell the truth about its database."""

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.web.server import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def client(migrated_engine, monkeypatch, test_database_url):
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        yield client


class TestHealth:
    def test_it_reports_ok_when_the_database_answers(self, client):
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_it_fails_when_the_database_does_not(self, monkeypatch):
        # Without the SELECT 1 this endpoint would only prove the port is open.
        monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://nobody@127.0.0.1:1/nothing")
        get_settings.cache_clear()

        with TestClient(create_app(), raise_server_exceptions=False) as client:
            assert client.get("/health").status_code == 500


class TestMiddleware:
    def test_every_response_carries_a_request_id(self, client):
        assert client.get("/health").headers["X-Request-ID"]

    def test_a_supplied_request_id_is_kept(self, client):
        response = client.get("/health", headers={"X-Request-ID": "abc123"})

        assert response.headers["X-Request-ID"] == "abc123"


class TestStatic:
    def test_the_stylesheet_is_served(self, client):
        response = client.get("/static/style.css")

        assert response.status_code == 200
        assert "text/css" in response.headers["content-type"]


class TestCommitBeforeAnswer:
    """A page that says "done" must only say it once the change is stored."""

    @staticmethod
    def failing_session():
        from sqlalchemy.exc import OperationalError

        from app.db.engine import get_session_factory

        session = get_session_factory()()
        try:
            yield session
            raise OperationalError("COMMIT", {}, Exception("connection lost"))
        finally:
            session.close()

    @pytest.mark.parametrize(
        ("method", "path"),
        [("post", "/abmelden/some-token"), ("get", "/k/pilot/bestaetigen/some-token")],
    )
    def test_a_failed_commit_never_reaches_the_client_as_success(
        self, migrated_engine, monkeypatch, test_database_url, method, path
    ):
        # One-click unsubscribe is not retried by the mail client: a 200 sent
        # before a failed commit would keep mailing someone who left.
        from app.web.deps import get_session

        monkeypatch.setenv("DATABASE_URL", test_database_url)
        get_settings.cache_clear()
        app = create_app()
        app.dependency_overrides[get_session] = self.failing_session

        with TestClient(app, raise_server_exceptions=False) as client:
            assert getattr(client, method)(path).status_code == 500


class TestHostileInput:
    """Crafted requests get a plain refusal, never a 500 and an error report."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/abmelden/abc%00"),
            ("post", "/abmelden/abc%00"),
            ("get", "/k/pilot/bestaetigen/abc%00"),
            ("get", "/s/abc%00"),
            ("get", "/creator/login/abc%1f"),
        ],
    )
    def test_control_characters_in_the_path_are_a_404(self, client, method, path):
        # PostgreSQL rejects a NUL byte in a string parameter; without this the
        # database driver raises and every such request is a 500.
        assert getattr(client, method)(path).status_code == 404

    @pytest.mark.parametrize("path", ["/webhooks/resend", "/k/pilot", "/creator/login"])
    def test_an_oversized_body_is_refused_before_it_is_read(self, client, path):
        # Nothing here needs more than a few kilobytes; a few concurrent
        # 100 MB bodies would otherwise take the single web instance down.
        response = client.post(path, content=b"x" * 100_000)

        assert response.status_code == 413
