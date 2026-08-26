from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class AnalysisModel(Base):
    __tablename__ = "analyses"
    __table_args__ = (Index("ix_analyses_machine_created", "machine_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    machine_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("machines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    condition: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class EvidencePackageModel(Base):
    __tablename__ = "evidence_packages"
    __table_args__ = (
        UniqueConstraint(
            "package_id",
            "package_digest_sha256",
            name="uq_evidence_packages_identity",
        ),
        Index(
            "ix_evidence_packages_machine_created",
            "machine_id",
            "created_at",
        ),
        Index("ix_evidence_packages_analysis_id", "analysis_id"),
    )

    package_id: Mapped[str] = mapped_column(String(37), primary_key=True)
    package_digest_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    machine_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("machines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    analysis_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("analyses.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class RetrievalBundleModel(Base):
    __tablename__ = "retrieval_bundles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["evidence_package_id", "evidence_package_digest_sha256"],
            [
                "evidence_packages.package_id",
                "evidence_packages.package_digest_sha256",
            ],
            name="fk_retrieval_bundles_evidence_identity",
            ondelete="RESTRICT",
        ),
        Index("ix_retrieval_bundles_evidence_package_id", "evidence_package_id"),
    )

    retrieval_bundle_digest_sha256: Mapped[str] = mapped_column(
        String(64),
        primary_key=True,
    )
    evidence_package_id: Mapped[str] = mapped_column(String(37), nullable=False)
    evidence_package_digest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    corpus_digest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model_id: Mapped[str] = mapped_column(String, nullable=False)
    embedding_model_revision: Mapped[str] = mapped_column(String, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)


class MaintenanceReportModel(Base):
    __tablename__ = "maintenance_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["evidence_package_id", "evidence_package_digest_sha256"],
            [
                "evidence_packages.package_id",
                "evidence_packages.package_digest_sha256",
            ],
            name="fk_maintenance_reports_evidence_identity",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_maintenance_reports_machine_generated",
            "machine_id",
            "generated_at",
            "report_id",
        ),
        Index("ix_maintenance_reports_evidence_package_id", "evidence_package_id"),
        Index(
            "ix_maintenance_reports_retrieval_digest",
            "retrieval_bundle_digest_sha256",
        ),
    )

    report_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    report_digest_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    machine_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("machines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    evidence_package_id: Mapped[str] = mapped_column(String(37), nullable=False)
    evidence_package_digest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    retrieval_bundle_digest_sha256: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "retrieval_bundles.retrieval_bundle_digest_sha256",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )
    generation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
