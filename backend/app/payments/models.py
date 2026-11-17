from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.database import Base

PAYMENT_STATUSES = ("pending", "succeeded", "failed", "manual_review")
BOOKING_DECISIONS = ("CONFIRMED", "ALREADY_CONFIRMED", "EXPIRED", "NOT_CONFIRMABLE")


def _sql_list(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class Payment(Base):
    """One payment attempt for a booking.

    No client personal data, credentials or card details are stored. The client idempotency key is
    stored only as a SHA-256 hash.
    """

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_payments_amount"),
        CheckConstraint("currency = 'UAH'", name="ck_payments_currency"),
        CheckConstraint(f"status IN ({_sql_list(PAYMENT_STATUSES)})", name="ck_payments_status"),
        CheckConstraint(
            f"booking_decision IS NULL OR booking_decision IN ({_sql_list(BOOKING_DECISIONS)})",
            name="ck_payments_booking_decision",
        ),
        CheckConstraint(
            "status <> 'succeeded' OR (provider_reference IS NOT NULL "
            "AND booking_decision IS NOT NULL "
            "AND booking_decision IN ('CONFIRMED', 'ALREADY_CONFIRMED'))",
            name="ck_payments_succeeded_requires_confirmation",
        ),
        CheckConstraint(
            "status <> 'manual_review' OR provider_reference IS NOT NULL",
            name="ck_payments_manual_review_requires_reference",
        ),
        CheckConstraint(
            "status NOT IN ('pending', 'failed') OR booking_decision IS NULL",
            name="ck_payments_undecided_without_booking_decision",
        ),
        Index("uq_payments_idempotency_key_hash", "idempotency_key_hash", unique=True),
        Index("uq_payments_provider_reference", "provider_reference", unique=True),
        Index(
            "uq_payments_one_pending_per_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "uq_payments_one_succeeded_per_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("status = 'succeeded'"),
        ),
        Index("ix_payments_booking_created", "booking_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("bookings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_reference: Mapped[str | None] = mapped_column(String(255))
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    booking_decision: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )
