from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.booking.models import Booking, BookingIdempotencyKey, BookingStatus


def get_booking(session: Session, booking_id: UUID, *, lock: bool = False) -> Booking | None:
    statement = select(Booking).where(Booking.id == booking_id)
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def psychologist_bookings(
    session: Session,
    psychologist_id: UUID,
    *,
    limit: int,
    offset: int,
    from_: datetime | None = None,
) -> tuple[list[Booking], int]:
    filters = [Booking.psychologist_id == psychologist_id]
    if from_ is not None:
        filters.append(Booking.starts_at >= from_)
    total = session.scalar(select(func.count()).select_from(Booking).where(*filters)) or 0
    bookings = list(
        session.scalars(
            select(Booking)
            .where(*filters)
            .order_by(Booking.starts_at.asc(), Booking.id.asc())
            .limit(limit)
            .offset(offset)
        )
    )
    return bookings, total


def expire_stale_holds(session: Session, psychologist_id: UUID) -> int:
    stale_holds = session.scalars(
        select(Booking)
        .where(
            Booking.psychologist_id == psychologist_id,
            Booking.status == BookingStatus.HELD,
            Booking.hold_expires_at <= func.clock_timestamp(),
        )
        .order_by(Booking.starts_at, Booking.id)
        .with_for_update()
    )
    bookings = list(stale_holds)
    for booking in bookings:
        booking.status = BookingStatus.EXPIRED
    session.flush()
    return len(bookings)


def add_booking(session: Session, booking: Booking) -> Booking:
    session.add(booking)
    session.flush()
    return booking


def get_active_booking_slots(
    session: Session,
    psychologist_id: UUID,
    starts_before: datetime,
    ends_after: datetime,
) -> list[tuple[UUID, datetime, datetime]]:
    statement = select(Booking.availability_slot_id, Booking.starts_at, Booking.ends_at).where(
        Booking.psychologist_id == psychologist_id,
        Booking.starts_at < starts_before,
        Booking.ends_at > ends_after,
        (Booking.status == BookingStatus.CONFIRMED)
        | (
            (Booking.status == BookingStatus.HELD)
            & (Booking.hold_expires_at > func.clock_timestamp())
        ),
    )
    return [tuple(row) for row in session.execute(statement)]


def payable_booking(session: Session, booking_id: UUID) -> Booking | None:
    return session.scalar(
        select(Booking).where(
            Booking.id == booking_id,
            Booking.status == BookingStatus.HELD,
            Booking.hold_expires_at > func.clock_timestamp(),
        )
    )


def get_booking_with_lock(session: Session, booking_id: UUID) -> Booking | None:
    return session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())


def claim_idempotency_key(
    session: Session, key_hash: str, request_hash: str
) -> tuple[BookingIdempotencyKey, bool]:
    session.execute(
        insert(BookingIdempotencyKey)
        .values(key_hash=key_hash, request_hash=request_hash)
        .on_conflict_do_nothing(index_elements=[BookingIdempotencyKey.key_hash])
    )
    record = session.scalar(
        select(BookingIdempotencyKey)
        .where(BookingIdempotencyKey.key_hash == key_hash)
        .with_for_update()
    )
    if record is None:
        raise RuntimeError("Idempotency record could not be loaded")
    return record, record.booking_id is None


def get_client_booking(
    session: Session, booking_id: UUID, access_token_hash: str
) -> Booking | None:
    return session.scalar(
        select(Booking).where(
            Booking.id == booking_id,
            Booking.client_access_token_hash == access_token_hash,
            Booking.client_access_token_expires_at > func.clock_timestamp(),
        )
    )


def set_client_access_token(
    session: Session, booking: Booking, token_hash: str, lifetime_seconds: int
) -> None:
    from datetime import timedelta

    booking.client_access_token_hash = token_hash
    booking.client_access_token_expires_at = func.clock_timestamp() + timedelta(
        seconds=lifetime_seconds
    )
    session.flush()
    session.refresh(booking)


def booking_for_access_recovery(
    session: Session, booking_id: UUID, *, lock: bool = False
) -> Booking | None:
    statement = select(Booking).where(Booking.id == booking_id)
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)
