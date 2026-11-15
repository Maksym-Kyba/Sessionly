"""Public availability operations for other modules."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.availability.models import AvailabilitySlot
from app.availability.repository import list_published_slots


def published_slots(
    session: Session, psychologist_id: UUID, from_time: datetime, to_time: datetime
) -> list[AvailabilitySlot]:
    return list_published_slots(session, psychologist_id, from_time, to_time)
