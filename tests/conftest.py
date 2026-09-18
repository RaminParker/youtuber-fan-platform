"""Shared fixtures.

Unit tests need nothing but the checked-in settings. Integration tests need a
real PostgreSQL, because the things worth testing here — unique constraints,
``ON CONFLICT``, cascades, advisory locks — have no equivalent in SQLite.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

from app.config import REPO_ROOT, Secrets, Settings, get_settings
from app.db import engine as db_engine
from app.db.models import Base
from app.services import set_services
from app.web.limits import limiter
from tests.fakes import FakeEmailClient

REQUIRED_SECRETS = {
    "DATABASE_URL": "postgresql+psycopg://app:app@localhost:5432/app_test",
    "SECRET_KEY": "test-secret-key",
}


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give every test the checked-in settings plus the two required secrets.

    The developer's own ``.env`` is switched off: a test that passes only on the
    machine that has the right dotenv file is not a test.
    """
    for model in (Settings, Secrets):
        monkeypatch.setitem(model.model_config, "env_file", None)
    for name, value in REQUIRED_SECRETS.items():
        monkeypatch.setenv(name, value)
    # Tests use example.org, whose null MX refuses all mail; and a test that
    # depends on the network is not a test. The DNS path has its own unit tests.
    monkeypatch.setenv("WEB__CHECK_ADDRESS_DNS", "false")
    get_settings.cache_clear()
    # The rate limiter counts per address in process memory, and every test
    # arrives from the same one. Without this, test number four is throttled.
    limiter.reset()
    yield
    get_settings.cache_clear()
    db_engine.reset_engine()


def alembic_config(url: str) -> Config:
    """Build an alembic config pointed at one database."""
    config = Config(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", url)
    return config


def from_env_file(name: str) -> str:
    """Read one value straight out of `.env`.

    The settings object deliberately ignores `.env` during tests, but this one
    value is read before any settings exist — and a developer who has copied
    `.env.example` should not also have to export it by hand.
    """
    path = REPO_ROOT / ".env"
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == name:
            return value.strip()
    return ""


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """The database the integration tests run against.

    Without one, the integration tests skip and the unit tests still run — so
    `uv run pytest` says something useful even with no database at hand.
    """
    url = os.environ.get("DATABASE_URL_TEST") or from_env_file("DATABASE_URL_TEST")
    if not url:
        pytest.skip(
            "no DATABASE_URL_TEST; run `docker compose up -d postgres` and copy .env.example"
        )
    return url


@pytest.fixture(scope="session")
def migrated_engine(test_database_url: str) -> Iterator[Engine]:
    """Bring the test database to head once, then hand out an engine."""
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def session(migrated_engine: Engine) -> Iterator[Session]:
    """A session whose work is rolled back when the test ends.

    The outer transaction is never committed, so tests cannot leak rows into
    each other even when the code under test commits.
    """
    connection = migrated_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def committed_database(
    migrated_engine: Engine, monkeypatch: pytest.MonkeyPatch, test_database_url: str
) -> Iterator[Engine]:
    """A database the code under test may really commit to, emptied afterwards.

    The rolled-back ``session`` fixture cannot serve the worker: it opens its
    own sessions through ``session_scope`` and commits them, deliberately, so
    that one bad row never rolls back the others. Testing that behaviour means
    letting it happen and cleaning up with a truncate.
    """
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    get_settings.cache_clear()
    db_engine.reset_engine()
    try:
        yield migrated_engine
    finally:
        tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
        with migrated_engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        db_engine.reset_engine()


@pytest.fixture
def mailer() -> FakeEmailClient:
    """Collects the mails a test would have sent."""
    return FakeEmailClient()


@pytest.fixture
def fake_services() -> Iterator[None]:
    """Guarantee that no test leaks a fake into the next one."""
    yield
    set_services(None)


@pytest.fixture
def scratch_database(test_database_url: str) -> Iterator[str]:
    """An empty database of its own, dropped afterwards.

    Migration tests must not run inside the database the other integration
    tests rely on: a downgrade would take their schema with it.
    """
    name = "app_migration_scratch"
    admin = create_engine(test_database_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield test_database_url.rsplit("/", 1)[0] + f"/{name}"
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
