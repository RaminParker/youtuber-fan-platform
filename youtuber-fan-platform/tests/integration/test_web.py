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
