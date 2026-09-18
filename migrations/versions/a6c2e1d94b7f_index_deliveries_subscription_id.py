"""index deliveries.subscription_id

The foreign key cascades from subscriptions; without an index every deleted
subscription scans the whole deliveries table.

Revision ID: a6c2e1d94b7f
Revises: f3180a7f18db
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a6c2e1d94b7f"
down_revision: str | None = "f3180a7f18db"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_deliveries_subscription_id"), "deliveries", ["subscription_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_deliveries_subscription_id"), table_name="deliveries")
