from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.database import Base


class AvailabilityRule(Base):
    __tablename__ = "availability_rules"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_availability_rules_weekday"),
        CheckConstraint("session_duration_minutes > 0", name="ck_availability_rules_duration"),
        CheckConstraint("price_minor >= 0", name="ck_availability_rules_price"),
        CheckConstraint("currency = 'UAH'", name="ck_availability_rules_currency"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until >= valid_from",
            name="ck_availability_rules_date_range",
        ),
        CheckConstraint("local_end > local_start", name="ck_availability_rules_time_range"),
        Index("ix_availability_rules_psychologist_active", "psychologist_id", "is_active"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    psychologist_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("psychologists.id", ondelete="RESTRICT"),
        nullable=False,
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    local_start: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    local_end: Mapped[time] = mapped_column(Time(timezone=False), nullable=False)
    session_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UAH", server_default="UAH")
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="ck_availability_slots_time_range"),
        CheckConstraint("price_minor >= 0", name="ck_availability_slots_price"),
        CheckConstraint("currency = 'UAH'", name="ck_availability_slots_currency"),
        CheckConstraint("state IN ('published', 'withdrawn')", name="ck_availability_slots_state"),
        UniqueConstraint(
            "psychologist_id", "starts_at", "ends_at", name="uq_availability_slots_identity"
        ),
        Index("ix_availability_slots_psychologist_starts", "psychologist_id", "starts_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    psychologist_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("psychologists.id", ondelete="RESTRICT"),
        nullable=False,
    )
    availability_rule_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("availability_rules.id", ondelete="RESTRICT"),
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="UAH", server_default="UAH")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="published", server_default="published")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
