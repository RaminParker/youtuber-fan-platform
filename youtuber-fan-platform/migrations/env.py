"""Alembic environment.

The URL comes from the application settings, never from alembic.ini, so that
`alembic upgrade head` and the running application can never disagree about
which database they mean. Tests override it programmatically.
"""

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.db.models import Base

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    """Return the configured URL, letting an explicit override win (tests)."""
    return config.get_main_option("sqlalchemy.url") or get_settings().secrets.database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run the migrations against a live database."""
    config.set_main_option("sqlalchemy.url", database_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
