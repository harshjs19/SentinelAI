from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class MaintenanceReportRequestModel(Base):
    __tablename__ = "maintenance_report_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('processing', 'completed')",
            name="ck_maintenance_report_requests_status",
        ),
        CheckConstraint(
            "(status = 'processing' AND claim_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL AND report_id IS NULL) OR "
            "(status = 'completed' AND claim_token IS NULL "
            "AND lease_expires_at IS NULL AND report_id IS NOT NULL)",
            name="ck_maintenance_report_requests_state_shape",
        ),
        Index(
            "ix_maintenance_report_requests_machine_created",
            "machine_id",
            "created_at",
        ),
    )

    idempotency_key_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    machine_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    modality: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    claim_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    report_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("maintenance_reports.report_id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
