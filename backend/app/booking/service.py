from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Sequence
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts import api as accounts_api
from app.availability import api as availability_api
from app.booking import repository
from app.booking.models import Booking, BookingStatus
from app.booking.schemas import (
    BookingConflict,
    BookingHold,
    ConfirmationOutcome,
    PayableBooking,
    PaymentResult,
)


@contextmanager
def _transaction(session: Session) -> Iterator[None]:
    """Join a caller transaction, or own one when called independently."""
    if session.in_transaction():
        yield
    else:
        with session.begin():
            yield


def create_hold(session: Session, slot_id: UUID) -> BookingHold:
    """Create an internal hold; public callers must be gated by email verification in Phase B."""
    hold: BookingHold
    try:
        with _transaction(session):
            initial_slot = availability_api.slot_for_booking(session, slot_id)
            if initial_slot is None:
                raise BookingConflict("Availability slot is unavailable")
            # Shared lock order: psychologist -> availability slot -> booking rows.
            psychologist = accounts_api.psychologist_by_id(
                session, initial_slot.psychologist_id, lock=True
            )
            if psychologist is None:
                raise BookingConflict("Availability slot is unavailable")
            slot = availability_api.slot_for_booking(session, slot_id, lock=True)
            if (
                slot is None
                or slot.psychologist_id != psychologist.id
                or slot.state != "published"
                or slot.starts_at <= session.scalar(func.clock_timestamp())
            ):
                raise BookingConflict("Availability slot is unavailable")

            repository.expire_stale_holds(session, psychologist.id)
            if slot.starts_at <= session.scalar(func.clock_timestamp()):
                raise BookingConflict("Availability slot is unavailable")
            duration_seconds = (slot.ends_at - slot.starts_at).total_seconds()
            if duration_seconds <= 0 or duration_seconds % 60:
                raise BookingConflict("Availability slot has an invalid duration")
            booking = Booking(
                availability_slot_id=slot.id,
                psychologist_id=psychologist.id,
                starts_at=slot.starts_at,
                ends_at=slot.ends_at,
                session_duration_minutes=int(duration_seconds // 60),
                price_minor=slot.price_minor,
                currency=slot.currency,
                status=BookingStatus.HELD,
            )
            repository.add_booking(session, booking)
            hold = BookingHold(
                id=booking.id,
                availability_slot_id=booking.availability_slot_id,
                psychologist_id=booking.psychologist_id,
                starts_at=booking.starts_at,
                ends_at=booking.ends_at,
                session_duration_minutes=booking.session_duration_minutes,
                price_minor=booking.price_minor,
                currency=booking.currency,
                status=booking.status,
                created_at=booking.created_at,
                hold_expires_at=booking.hold_expires_at,
            )
    except IntegrityError as exc:
        raise BookingConflict("Availability slot is unavailable") from exc
    return hold


def get_payable_booking(session: Session, booking_id: UUID) -> PayableBooking | None:
    booking = repository.payable_booking(session, booking_id)
    if booking is None:
        return None
    return PayableBooking(
        booking_id=booking.id,
        amount_minor=booking.price_minor,
        currency=booking.currency,
        hold_expires_at=booking.hold_expires_at,
    )


def confirm_held_booking(
    session: Session, booking_id: UUID, payment_result: PaymentResult
) -> ConfirmationOutcome:
    """Apply a payment result only while its hold is still active at database execution time."""
    if not isinstance(payment_result, PaymentResult) or not isinstance(
        payment_result.succeeded, bool
    ):
        return ConfirmationOutcome.NOT_CONFIRMABLE
    if payment_result.payment_reference is not None and not isinstance(
        payment_result.payment_reference, str
    ):
        return ConfirmationOutcome.NOT_CONFIRMABLE
    payment_reference = (payment_result.payment_reference or "").strip()
    if len(payment_reference) > 255:
        return ConfirmationOutcome.NOT_CONFIRMABLE
    with _transaction(session):
        unwrapped = repository.get_booking(session, booking_id)
        if unwrapped is None:
            return ConfirmationOutcome.NOT_CONFIRMABLE
        psychologist = accounts_api.psychologist_by_id(
            session, unwrapped.psychologist_id, lock=True
        )
        if psychologist is None:
            return ConfirmationOutcome.NOT_CONFIRMABLE
        booking = repository.get_booking_with_lock(session, booking_id)
        if booking is None:
            return ConfirmationOutcome.NOT_CONFIRMABLE
        if booking.status == BookingStatus.CONFIRMED:
            if booking.payment_reference == payment_reference:
                return ConfirmationOutcome.ALREADY_CONFIRMED
            return ConfirmationOutcome.NOT_CONFIRMABLE
        if booking.status == BookingStatus.EXPIRED:
            return ConfirmationOutcome.EXPIRED
        if booking.status != BookingStatus.HELD:
            return ConfirmationOutcome.NOT_CONFIRMABLE

        now = session.scalar(func.clock_timestamp())
        if now is None or booking.hold_expires_at <= now:
            booking.status = BookingStatus.EXPIRED
            session.flush()
            return ConfirmationOutcome.EXPIRED
        if not payment_result.succeeded or not payment_reference:
            return ConfirmationOutcome.NOT_CONFIRMABLE

        try:
            with session.begin_nested():
                booking.status = BookingStatus.CONFIRMED
                booking.confirmed_at = now
                booking.payment_reference = payment_reference
                session.flush()
        except IntegrityError:
            return ConfirmationOutcome.NOT_CONFIRMABLE
        return ConfirmationOutcome.CONFIRMED


def available_slot_ids(
    session: Session,
    psychologist_id: UUID,
    slots: Sequence[tuple[UUID, datetime, datetime]],
) -> set[UUID]:
    if not slots:
        return set()
    intervals = repository.get_active_booking_slots(
        session,
        psychologist_id,
        max(ends_at for _, _, ends_at in slots),
        min(starts_at for _, starts_at, _ in slots),
    )
    unavailable = {
        candidate_slot_id
        for _, booking_start, booking_end in intervals
        for candidate_slot_id, starts_at, ends_at in slots
        if booking_start < ends_at and starts_at < booking_end
    }
    return {slot_id for slot_id, _, _ in slots} - unavailable
