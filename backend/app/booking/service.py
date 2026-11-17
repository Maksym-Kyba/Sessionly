from contextlib import contextmanager
import hashlib
import secrets
from datetime import datetime
from typing import Iterator, Sequence
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts import api as accounts_api
from app.availability import api as availability_api
from app.core.config import settings
from app.booking import repository
from app.booking.models import Booking, BookingStatus
from app.booking.schemas import (
    BookingConflict,
    BookingHold,
    ClientBooking,
    ConfirmationOutcome,
    PayableBooking,
    PaymentResult,
    PublicBookingCreation,
    PsychologistBooking,
    PsychologistBookingPage,
)
from app.notifications import api as notifications_api


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


class IdempotencyConflict(Exception):
    """Raised when an idempotency key is reused for a different request."""


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _booking_creation(booking: Booking, token: str | None, replay: bool) -> PublicBookingCreation:
    return PublicBookingCreation(
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
        client_access_token=token,
        access_token_expires_at=booking.client_access_token_expires_at,
        idempotent_replay=replay,
    )


def create_verified_hold(
    session: Session,
    slot_id: UUID,
    booking_verification_token: str,
    idempotency_key: str,
) -> PublicBookingCreation:
    if not 16 <= len(idempotency_key) <= 128:
        raise ValueError("Idempotency-Key must contain between 16 and 128 characters")
    key_hash = _token_hash(idempotency_key)
    request_hash = _token_hash(str(slot_id))
    result: PublicBookingCreation
    with _transaction(session):
        idempotency_record, is_new = repository.claim_idempotency_key(
            session, key_hash, request_hash
        )
        if idempotency_record.request_hash != request_hash:
            raise IdempotencyConflict
        if not is_new and idempotency_record.booking_id is not None:
            existing = repository.get_booking(session, idempotency_record.booking_id)
            if existing is None:
                raise RuntimeError("Idempotent booking record references a missing booking")
            supplied_grant_hash = _token_hash(booking_verification_token)
            if idempotency_record.verification_grant_hash == supplied_grant_hash:
                client_email, _ = notifications_api.validate_consumed_booking_verification(
                    session, booking_verification_token, existing.psychologist_id
                )
                raw_access_token = None
            else:
                client_email, _ = notifications_api.consume_booking_verification(
                    session, booking_verification_token, existing.psychologist_id
                )
                raw_access_token = secrets.token_urlsafe(32)
            if client_email != existing.client_email:
                raise notifications_api.InvalidVerificationToken
            psychologist = accounts_api.psychologist_by_id(
                session, existing.psychologist_id, lock=True
            )
            existing = repository.get_booking_with_lock(session, existing.id)
            now = session.scalar(func.clock_timestamp())
            if existing is None or psychologist is None or now is None:
                raise notifications_api.InvalidVerificationToken
            if existing.status == BookingStatus.HELD and existing.hold_expires_at <= now:
                existing.status = BookingStatus.EXPIRED
            if raw_access_token is not None:
                idempotency_record.verification_grant_hash = supplied_grant_hash
                repository.set_client_access_token(
                    session,
                    existing,
                    _token_hash(raw_access_token),
                    settings.client_booking_token_ttl_seconds,
                )
            return _booking_creation(existing, raw_access_token, True)

        slot = availability_api.slot_for_booking(session, slot_id)
        if slot is None:
            raise BookingConflict("Availability slot is unavailable")
        client_email, _ = notifications_api.consume_booking_verification(
            session, booking_verification_token, slot.psychologist_id
        )
        hold = create_hold(session, slot_id)
        booking = repository.get_booking(session, hold.id)
        if booking is None:
            raise RuntimeError("Created booking could not be loaded")
        booking.client_email = client_email
        raw_access_token = secrets.token_urlsafe(32)
        repository.set_client_access_token(
            session,
            booking,
            _token_hash(raw_access_token),
            settings.client_booking_token_ttl_seconds,
        )
        idempotency_record.verification_grant_hash = _token_hash(booking_verification_token)
        idempotency_record.booking_id = booking.id
        session.flush()
        result = _booking_creation(booking, raw_access_token, False)
    return result


def recover_client_access_token(
    session: Session, booking_id: UUID, booking_verification_token: str
) -> tuple[str, datetime] | None:
    raw_access_token = secrets.token_urlsafe(32)
    with _transaction(session):
        initial_booking = repository.booking_for_access_recovery(session, booking_id)
        if initial_booking is None:
            raise notifications_api.InvalidVerificationToken
        verified_email, psychologist_id = notifications_api.consume_booking_verification(
            session, booking_verification_token, initial_booking.psychologist_id
        )
        psychologist = accounts_api.psychologist_by_id(session, psychologist_id, lock=True)
        if psychologist is None:
            raise notifications_api.InvalidVerificationToken
        booking = repository.booking_for_access_recovery(session, booking_id, lock=True)
        if (
            booking is None
            or booking.psychologist_id != psychologist_id
            or booking.client_email != verified_email
        ):
            raise notifications_api.InvalidVerificationToken
        repository.set_client_access_token(
            session,
            booking,
            _token_hash(raw_access_token),
            settings.client_booking_token_ttl_seconds,
        )
        return raw_access_token, booking.client_access_token_expires_at


def get_client_booking(
    session: Session, booking_id: UUID, client_access_token: str
) -> ClientBooking | None:
    with _transaction(session):
        token_hash = _token_hash(client_access_token)
        booking = repository.get_client_booking(session, booking_id, token_hash)
        if booking is None:
            return None
        psychologist = accounts_api.psychologist_by_id(session, booking.psychologist_id, lock=True)
        if psychologist is None:
            return None
        booking = repository.get_booking_with_lock(session, booking_id)
        now = session.scalar(func.clock_timestamp())
        if (
            booking is None
            or booking.client_access_token_hash != token_hash
            or booking.client_access_token_expires_at is None
            or booking.client_access_token_expires_at <= now
        ):
            return None
        if booking.status == BookingStatus.HELD and booking.hold_expires_at <= now:
            booking.status = BookingStatus.EXPIRED
            session.flush()
        return ClientBooking(
            id=booking.id,
            status=booking.status,
            starts_at=booking.starts_at,
            ends_at=booking.ends_at,
            session_duration_minutes=booking.session_duration_minutes,
            price_minor=booking.price_minor,
            currency=booking.currency,
            hold_expires_at=booking.hold_expires_at,
            created_at=booking.created_at,
        )


def get_psychologist_booking(
    session: Session, booking_id: UUID, psychologist_id: UUID
) -> ClientBooking | None:
    booking = repository.get_booking(session, booking_id)
    if booking is None or booking.psychologist_id != psychologist_id:
        return None
    now = session.scalar(func.clock_timestamp())
    status_value = booking.status
    if status_value == BookingStatus.HELD and booking.hold_expires_at <= now:
        status_value = BookingStatus.EXPIRED
    return ClientBooking(
        id=booking.id,
        status=status_value,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        session_duration_minutes=booking.session_duration_minutes,
        price_minor=booking.price_minor,
        currency=booking.currency,
        hold_expires_at=booking.hold_expires_at,
        created_at=booking.created_at,
    )


def list_psychologist_bookings(
    session: Session, psychologist_id: UUID, *, limit: int, offset: int
) -> PsychologistBookingPage:
    bookings, total = repository.psychologist_bookings(
        session, psychologist_id, limit=limit, offset=offset
    )
    now = session.scalar(func.clock_timestamp())
    items = [
        PsychologistBooking(
            id=booking.id,
            status=(
                BookingStatus.EXPIRED
                if booking.status == BookingStatus.HELD and booking.hold_expires_at <= now
                else booking.status
            ),
            starts_at=booking.starts_at,
            ends_at=booking.ends_at,
            client_email=booking.client_email,
            session_duration_minutes=booking.session_duration_minutes,
            price_minor=booking.price_minor,
            currency=booking.currency,
            created_at=booking.created_at,
        )
        for booking in bookings
    ]
    return PsychologistBookingPage(items=items, total=total, limit=limit, offset=offset)
