from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.accounts.models import AuthSession, GoogleIdentity, OAuthTransaction, Psychologist


def get_by_public_id(session: Session, public_id: str) -> Psychologist | None:
    return session.scalar(select(Psychologist).where(Psychologist.public_id == public_id))


def get_by_id(
    session: Session, psychologist_id: UUID, *, lock: bool = False
) -> Psychologist | None:
    statement = select(Psychologist).where(Psychologist.id == psychologist_id)
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def get_google_identity(session: Session, google_subject: str) -> GoogleIdentity | None:
    return session.scalar(
        select(GoogleIdentity).where(GoogleIdentity.google_subject == google_subject)
    )


def get_by_email(session: Session, email: str) -> Psychologist | None:
    return session.scalar(
        select(Psychologist).where(func.lower(Psychologist.email) == email.lower())
    )


def add_oauth_transaction(session: Session, transaction: OAuthTransaction) -> None:
    session.add(transaction)


def add_psychologist(session: Session, psychologist: Psychologist) -> None:
    session.add(psychologist)
    session.flush()


def add_google_identity(session: Session, identity: GoogleIdentity) -> None:
    session.add(identity)


def add_auth_session(session: Session, auth_session: AuthSession) -> None:
    session.add(auth_session)


def get_oauth_transaction_for_update(session: Session, state_hash: str) -> OAuthTransaction | None:
    return session.scalar(
        select(OAuthTransaction).where(OAuthTransaction.state_hash == state_hash).with_for_update()
    )


def get_active_session(session: Session, token_hash: str, now) -> AuthSession | None:
    return session.scalar(
        select(AuthSession).where(
            AuthSession.session_token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
    )


def get_session_by_token_hash(session: Session, token_hash: str) -> AuthSession | None:
    return session.scalar(select(AuthSession).where(AuthSession.session_token_hash == token_hash))


def delete_expired_oauth_transactions(session: Session, now: datetime) -> None:
    session.execute(delete(OAuthTransaction).where(OAuthTransaction.expires_at <= now))
