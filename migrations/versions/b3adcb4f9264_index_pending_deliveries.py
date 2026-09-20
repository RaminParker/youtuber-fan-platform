"""index pending deliveries

Revision ID: b3adcb4f9264
Revises: a6c2e1d94b7f
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3adcb4f9264"
down_revision: str | None = "a6c2e1d94b7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """The batch loop asks for the next unsent rows of one mailing, per batch."""
    op.create_index(
        "ix_deliveries_pending",
        "deliveries",
        ["mailing_id", "id"],
        unique=False,
        postgresql_where=sa.text("sent_at IS NULL"),
    )


def downgrade() -> None:
    """Drop it again."""
    op.drop_index(
        "ix_deliveries_pending",
        table_name="deliveries",
        postgresql_where=sa.text("sent_at IS NULL"),
    )
