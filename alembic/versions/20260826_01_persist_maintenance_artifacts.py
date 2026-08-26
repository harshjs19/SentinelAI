"""Persist complete maintenance workflow artifacts.

Revision ID: 20260826_01
Revises: 20260823_01
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260826_01"
down_revision: str | None = "20260823_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("machine_id", sa.Uuid(), nullable=False),
        sa.Column("condition", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload_schema_version", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["machine_id"],
            ["machines.id"],
            name=op.f("fk_analyses_machine_id_machines"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analyses")),
    )
    op.create_index(
        "ix_analyses_machine_created",
        "analyses",
        ["machine_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "evidence_packages",
        sa.Column("package_id", sa.String(length=37), nullable=False),
        sa.Column("package_digest_sha256", sa.String(length=64), nullable=False),
        sa.Column("machine_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["analyses.id"],
            name=op.f("fk_evidence_packages_analysis_id_analyses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["machine_id"],
            ["machines.id"],
            name=op.f("fk_evidence_packages_machine_id_machines"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("package_id", name=op.f("pk_evidence_packages")),
        sa.UniqueConstraint(
            "package_digest_sha256",
            name=op.f("uq_evidence_packages_package_digest_sha256"),
        ),
        sa.UniqueConstraint(
            "package_id",
            "package_digest_sha256",
            name="uq_evidence_packages_identity",
        ),
    )
    op.create_index(
        "ix_evidence_packages_analysis_id",
        "evidence_packages",
        ["analysis_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_packages_machine_created",
        "evidence_packages",
        ["machine_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "retrieval_bundles",
        sa.Column("retrieval_bundle_digest_sha256", sa.String(length=64), nullable=False),
        sa.Column("evidence_package_id", sa.String(length=37), nullable=False),
        sa.Column("evidence_package_digest_sha256", sa.String(length=64), nullable=False),
        sa.Column("corpus_digest_sha256", sa.String(length=64), nullable=False),
        sa.Column("embedding_model_id", sa.String(), nullable=False),
        sa.Column("embedding_model_revision", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_package_id", "evidence_package_digest_sha256"],
            [
                "evidence_packages.package_id",
                "evidence_packages.package_digest_sha256",
            ],
            name="fk_retrieval_bundles_evidence_identity",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "retrieval_bundle_digest_sha256",
            name=op.f("pk_retrieval_bundles"),
        ),
    )
    op.create_index(
        "ix_retrieval_bundles_evidence_package_id",
        "retrieval_bundles",
        ["evidence_package_id"],
        unique=False,
    )

    op.create_table(
        "maintenance_reports",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("report_digest_sha256", sa.String(length=64), nullable=False),
        sa.Column("machine_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_package_id", sa.String(length=37), nullable=False),
        sa.Column("evidence_package_digest_sha256", sa.String(length=64), nullable=False),
        sa.Column("retrieval_bundle_digest_sha256", sa.String(length=64), nullable=False),
        sa.Column("generation_status", sa.String(length=32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["evidence_package_id", "evidence_package_digest_sha256"],
            [
                "evidence_packages.package_id",
                "evidence_packages.package_digest_sha256",
            ],
            name="fk_maintenance_reports_evidence_identity",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["machine_id"],
            ["machines.id"],
            name=op.f("fk_maintenance_reports_machine_id_machines"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_bundle_digest_sha256"],
            ["retrieval_bundles.retrieval_bundle_digest_sha256"],
            name=op.f("fk_maintenance_reports_retrieval_bundle_digest_sha256_retrieval_bundles"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("report_id", name=op.f("pk_maintenance_reports")),
        sa.UniqueConstraint(
            "report_digest_sha256",
            name=op.f("uq_maintenance_reports_report_digest_sha256"),
        ),
    )
    op.create_index(
        "ix_maintenance_reports_evidence_package_id",
        "maintenance_reports",
        ["evidence_package_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_reports_machine_generated",
        "maintenance_reports",
        ["machine_id", "generated_at", "report_id"],
        unique=False,
    )
    op.create_index(
        "ix_maintenance_reports_retrieval_digest",
        "maintenance_reports",
        ["retrieval_bundle_digest_sha256"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_maintenance_reports_retrieval_digest",
        table_name="maintenance_reports",
    )
    op.drop_index(
        "ix_maintenance_reports_machine_generated",
        table_name="maintenance_reports",
    )
    op.drop_index(
        "ix_maintenance_reports_evidence_package_id",
        table_name="maintenance_reports",
    )
    op.drop_table("maintenance_reports")
    op.drop_index(
        "ix_retrieval_bundles_evidence_package_id",
        table_name="retrieval_bundles",
    )
    op.drop_table("retrieval_bundles")
    op.drop_index(
        "ix_evidence_packages_machine_created",
        table_name="evidence_packages",
    )
    op.drop_index(
        "ix_evidence_packages_analysis_id",
        table_name="evidence_packages",
    )
    op.drop_table("evidence_packages")
    op.drop_index("ix_analyses_machine_created", table_name="analyses")
    op.drop_table("analyses")
