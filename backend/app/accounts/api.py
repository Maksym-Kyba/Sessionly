"""Public interface for account data used by other modules."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.accounts.models import Psychologist
from app.accounts.service import get_public_psychologist, get_psychologist


def psychologist_by_public_id(session: Session, public_id: str) -> Psychologist | None:
    return get_public_psychologist(session, public_id)


def psychologist_by_id(
    session: Session, psychologist_id: UUID, *, lock: bool = False
) -> Psychologist | None:
    return get_psychologist(session, psychologist_id, lock=lock)
