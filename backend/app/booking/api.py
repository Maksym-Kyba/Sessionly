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
    PublicBookingCreation,
    PsychologistBookingPage,
)
from app.notifications.api import InvalidVerificationToken

__all__ = [
    "BookingConflict",
    "BookingHold",
    "ConfirmationOutcome",
    "IdempotencyConflict",
    "InvalidVerificationToken",
    "PayableBooking",
    "PaymentResult",
    "PublicBookingCreation",
    "available_slot_ids",
    "confirm_held_booking",
    "create_hold",
    "get_payable_booking",
    "get_client_booking",
    "get_psychologist_booking",
    "list_psychologist_bookings",
    "recover_client_access_token",
    "create_verified_hold",
]

IdempotencyConflict = service.IdempotencyConflict


def create_hold(session: Session, slot_id: UUID) -> BookingHold:
    """Create a reservation internally; Phase B must verify client email before calling."""
    return service.create_hold(session, slot_id)


def create_verified_hold(
    session: Session, slot_id: UUID, booking_verification_token: str, idempotency_key: str
) -> PublicBookingCreation:
    return service.create_verified_hold(
        session, slot_id, booking_verification_token, idempotency_key
    )


def recover_client_access_token(
    session: Session, booking_id: UUID, booking_verification_token: str
):
    return service.recover_client_access_token(session, booking_id, booking_verification_token)


def get_client_booking(session: Session, booking_id: UUID, access_token: str):
    return service.get_client_booking(session, booking_id, access_token)


def get_psychologist_booking(session: Session, booking_id: UUID, psychologist_id: UUID):
    return service.get_psychologist_booking(session, booking_id, psychologist_id)


def list_psychologist_bookings(
    session: Session, psychologist_id: UUID, *, limit: int, offset: int
) -> PsychologistBookingPage:
    return service.list_psychologist_bookings(session, psychologist_id, limit=limit, offset=offset)


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
