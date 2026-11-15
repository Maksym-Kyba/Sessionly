from sqlalchemy import select
from uuid import UUID

from sqlalchemy.orm import Session

from app.accounts.models import Psychologist


def get_by_public_id(session: Session, public_id: str) -> Psychologist | None:
    return session.scalar(select(Psychologist).where(Psychologist.public_id == public_id))


def get_by_id(session: Session, psychologist_id: UUID, *, lock: bool = False) -> Psychologist | None:
    statement = select(Psychologist).where(Psychologist.id == psychologist_id)
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)
