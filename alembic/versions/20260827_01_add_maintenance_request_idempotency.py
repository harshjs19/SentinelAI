"""Add durable maintenance request idempotency.

Revision ID: 20260827_01
Revises: 20260826_01
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260827_01"
down_revision: str | None = "20260826_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "maintenance_report_requests",
        sa.Column("idempotency_key_digest", sa.String(length=64), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("machine_id", sa.Uuid(), nullable=False),
        sa.Column("modality", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("claim_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("report_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(status = 'processing' AND claim_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND report_id IS NULL) OR "
            "(status = 'completed' AND claim_token IS NULL "
            "AND lease_expires_at IS NULL AND report_id IS NOT NULL)",
            name="ck_maintenance_report_requests_state_shape",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'completed')",
            name="ck_maintenance_report_requests_status",
        ),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["maintenance_reports.report_id"],
            name=op.f("fk_maintenance_report_requests_report_id_maintenance_reports"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "idempotency_key_digest",
            name=op.f("pk_maintenance_report_requests"),
        ),
        sa.UniqueConstraint(
            "report_id",
            name=op.f("uq_maintenance_report_requests_report_id"),
        ),
    )
    op.create_index(
        "ix_maintenance_report_requests_machine_created",
        "maintenance_report_requests",
        ["machine_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_maintenance_report_requests_machine_created",
        table_name="maintenance_report_requests",
    )
    op.drop_table("maintenance_report_requests")
