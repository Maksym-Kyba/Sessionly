from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class BookingConflict(Exception):
    """Raised when a requested availability interval cannot be reserved."""


class ConfirmationOutcome(StrEnum):
    CONFIRMED = "CONFIRMED"
    ALREADY_CONFIRMED = "ALREADY_CONFIRMED"
    EXPIRED = "EXPIRED"
    NOT_CONFIRMABLE = "NOT_CONFIRMABLE"


@dataclass(frozen=True)
class BookingHold:
    id: UUID
    availability_slot_id: UUID
    psychologist_id: UUID
    starts_at: datetime
    ends_at: datetime
    session_duration_minutes: int
    price_minor: int
    currency: str
    status: str
    created_at: datetime
    hold_expires_at: datetime


@dataclass(frozen=True)
class PayableBooking:
    booking_id: UUID
    amount_minor: int
    currency: str
    hold_expires_at: datetime


@dataclass(frozen=True)
class PaymentResult:
    payment_reference: str | None
    succeeded: bool
