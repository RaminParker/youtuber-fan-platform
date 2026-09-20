"""ledger keeps the price it booked

Revision ID: 96da9aa50afa
Revises: b3adcb4f9264
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "96da9aa50afa"
down_revision: str | None = "b3adcb4f9264"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Every ledger line says what it was billed at, and what came from cache."""
    op.add_column(
        "llm_calls", sa.Column("tokens_cached", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "llm_calls",
        sa.Column("tokens_cache_write", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "llm_calls",
        sa.Column(
            "price_input", sa.Numeric(precision=12, scale=6), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "llm_calls",
        sa.Column(
            "price_output", sa.Numeric(precision=12, scale=6), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "llm_calls",
        sa.Column("price_source", sa.String(length=128), server_default="unknown", nullable=False),
    )


def downgrade() -> None:
    """Drop them again."""
    op.drop_column("llm_calls", "price_source")
    op.drop_column("llm_calls", "price_output")
    op.drop_column("llm_calls", "price_input")
    op.drop_column("llm_calls", "tokens_cache_write")
    op.drop_column("llm_calls", "tokens_cached")
