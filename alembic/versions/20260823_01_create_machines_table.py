"""Create machines table.

Revision ID: 20260823_01
Revises:
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260823_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "machines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("asset_type", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_machines")),
    )


def downgrade() -> None:
    op.drop_table("machines")
