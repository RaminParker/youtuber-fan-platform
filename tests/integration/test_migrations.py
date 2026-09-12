"""The schema must be reachable from an empty database, and reversible."""

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect

from app.db.models import Base
from tests.conftest import alembic_config

pytestmark = pytest.mark.integration

EXPECTED_TABLES = {
    "creators",
    "sources",
    "appearances",
    "transcripts",
    "analyses",
    "subscribers",
    "subscriptions",
    "mailings",
    "deliveries",
    "llm_calls",
    "job_runs",
}


def table_names(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_upgrade_creates_every_table(scratch_database):
    command.upgrade(alembic_config(scratch_database), "head")

    assert table_names(scratch_database) >= EXPECTED_TABLES


def test_downgrade_leaves_nothing_behind(scratch_database):
    config = alembic_config(scratch_database)
    command.upgrade(config, "head")

    command.downgrade(config, "base")

    # Only alembic's own bookkeeping table may survive.
    assert table_names(scratch_database) <= {"alembic_version"}


def test_the_migration_matches_the_models(scratch_database):
    """A model changed without a migration would be caught here, not in production."""
    command.upgrade(alembic_config(scratch_database), "head")

    assert table_names(scratch_database) - {"alembic_version"} == set(Base.metadata.tables)
