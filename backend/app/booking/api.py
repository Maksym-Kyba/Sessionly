"""Internal public interface for booking reservations and payment integration."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.booking import service
from app.booking.schemas import (
    BookingConflict,
    BookingHold,
    ConfirmationOutcome,
    PayableBooking,
    PaymentResult,
)

__all__ = [
    "BookingConflict",
    "BookingHold",
    "ConfirmationOutcome",
    "PayableBooking",
    "PaymentResult",
    "available_slot_ids",
    "confirm_held_booking",
    "create_hold",
    "get_payable_booking",
]


def create_hold(session: Session, slot_id: UUID) -> BookingHold:
    """Create a reservation internally; Phase B must verify client email before calling."""
    return service.create_hold(session, slot_id)


def available_slot_ids(
    session: Session, psychologist_id: UUID, slots: list[tuple[UUID, datetime, datetime]]
) -> set[UUID]:
    return service.available_slot_ids(session, psychologist_id, slots)


def get_payable_booking(session: Session, booking_id: UUID) -> PayableBooking | None:
    return service.get_payable_booking(session, booking_id)


def confirm_held_booking(
    session: Session, booking_id: UUID, payment_result: PaymentResult
) -> ConfirmationOutcome:
    return service.confirm_held_booking(session, booking_id, payment_result)
