from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.booking.models import Booking, BookingStatus


def get_booking(session: Session, booking_id: UUID, *, lock: bool = False) -> Booking | None:
    statement = select(Booking).where(Booking.id == booking_id)
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


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
