"""Public availability operations for other modules."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.availability.models import AvailabilitySlot
from app.availability.repository import list_published_slots
from app.availability.repository import get_slot


@dataclass(frozen=True)
class SlotForBooking:
    id: UUID
    psychologist_id: UUID
    starts_at: datetime
    ends_at: datetime
    price_minor: int
    currency: str
    state: str


def slot_for_booking(
    session: Session, slot_id: UUID, *, lock: bool = False
) -> SlotForBooking | None:
    slot = get_slot(session, slot_id, lock=lock)
    if slot is None:
        return None
    return SlotForBooking(
        id=slot.id,
        psychologist_id=slot.psychologist_id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        price_minor=slot.price_minor,
        currency=slot.currency,
        state=slot.state,
    )


def published_slots(
    session: Session, psychologist_id: UUID, from_time: datetime, to_time: datetime
) -> list[AvailabilitySlot]:
    return list_published_slots(session, psychologist_id, from_time, to_time)
