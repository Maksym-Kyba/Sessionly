from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.database import Base


class BookingStatus(StrEnum):
    HELD = "HELD"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_bookings_time_range"),
        CheckConstraint("session_duration_minutes > 0", name="ck_bookings_duration"),
        CheckConstraint("price_minor >= 0", name="ck_bookings_price"),
        CheckConstraint("currency = 'UAH'", name="ck_bookings_currency"),
        CheckConstraint("status IN ('HELD', 'CONFIRMED', 'EXPIRED')", name="ck_bookings_status"),
        UniqueConstraint("payment_reference", name="uq_bookings_payment_reference"),
        UniqueConstraint("client_access_token_hash", name="uq_bookings_client_access_token_hash"),
        CheckConstraint(
            "(client_access_token_hash IS NULL) = (client_access_token_expires_at IS NULL)",
            name="ck_bookings_access_token_fields",
        ),
        Index(
            "ix_bookings_expiration_candidates",
            "psychologist_id",
            "hold_expires_at",
            postgresql_where=text("status = 'HELD'"),
        ),
        Index("ix_bookings_psychologist_status_starts", "psychologist_id", "status", "starts_at"),
        ExcludeConstraint(
            ("psychologist_id", "="),
            (text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            where=text("status IN ('HELD', 'CONFIRMED')"),
            using="gist",
            name="ex_bookings_no_overlapping_active_appointments",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    availability_slot_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("availability_slots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    psychologist_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("psychologists.id", ondelete="RESTRICT"),
        nullable=False,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    session_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    client_email: Mapped[str | None] = mapped_column(String(320))
    client_access_token_hash: Mapped[str | None] = mapped_column(String(64))
    client_access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=BookingStatus.HELD)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.statement_timestamp(), nullable=False
    )
    hold_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("(statement_timestamp() + INTERVAL '15 minutes')"),
        nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.clock_timestamp(),
        onupdate=func.clock_timestamp(),
        nullable=False,
    )


class BookingIdempotencyKey(Base):
    __tablename__ = "booking_idempotency_keys"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_grant_hash: Mapped[str | None] = mapped_column(String(64))
    booking_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bookings.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.statement_timestamp(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_booking_idempotency_booking"),
        CheckConstraint(
            "(booking_id IS NULL) = (verification_grant_hash IS NULL)",
            name="ck_booking_idempotency_completion_fields",
        ),
        Index("ix_booking_idempotency_created_at", "created_at"),
    )
