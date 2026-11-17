from uuid import UUID

from sqlalchemy.orm import Session

from app.accounts import repository
from app.accounts.models import Psychologist


def get_public_psychologist(session: Session, public_id: str) -> Psychologist | None:
    return repository.get_by_public_id(session, public_id)


def get_psychologist(
    session: Session, psychologist_id: UUID, *, lock: bool = False
) -> Psychologist | None:
    return repository.get_by_id(session, psychologist_id, lock=lock)


def update_psychologist_profile(
    session: Session, psychologist_id: UUID, fields: dict[str, str]
) -> Psychologist | None:
    with session.begin():
        psychologist = repository.get_by_id(session, psychologist_id, lock=True)
        if psychologist is None:
            return None
        repository.update_psychologist_profile(session, psychologist, fields)
        if "time_zone" in fields:
            # Changing the IANA zone changes how weekly rules map to future UTC slots.
            # Refresh through Availability's public interface in this transaction.
            from app.availability import api as availability_api

            availability_api.refresh_slots(session, psychologist_id)
    return psychologist
