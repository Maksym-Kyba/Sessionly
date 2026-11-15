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
