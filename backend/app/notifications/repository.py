from datetime import timedelta
from uuid import UUID

from sqlalchemy import case, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.notifications.models import (
    BookingVerificationGrant,
    EmailVerificationToken,
    PublicRateLimitBucket,
)


def increment_rate_limit(session: Session, key_hash: str, *, window_seconds: int = 3600) -> int:
    table = PublicRateLimitBucket.__table__
    expired_window = table.c.window_started_at <= func.clock_timestamp() - timedelta(
        seconds=window_seconds
    )
    statement = insert(PublicRateLimitBucket).values(
        key_hash=key_hash,
        window_started_at=func.clock_timestamp(),
        request_count=1,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.key_hash],
        set_={
            "window_started_at": case(
                (expired_window, func.clock_timestamp()), else_=table.c.window_started_at
            ),
            "request_count": case((expired_window, 1), else_=table.c.request_count + 1),
        },
    ).returning(table.c.request_count)
    return int(session.scalar(statement))


def prune_expired_public_state(session: Session) -> None:
    retention = func.clock_timestamp() - timedelta(days=7)
    session.execute(
        delete(EmailVerificationToken).where(EmailVerificationToken.expires_at < retention)
    )
    session.execute(
        delete(BookingVerificationGrant).where(BookingVerificationGrant.expires_at < retention)
    )
    session.execute(
        delete(PublicRateLimitBucket).where(
            PublicRateLimitBucket.window_started_at < func.clock_timestamp() - timedelta(days=2)
        )
    )


def add_email_verification(
    session: Session,
    psychologist_id: UUID,
    email: str,
    token_hash: str,
    lifetime_seconds: int,
) -> EmailVerificationToken:
    token = EmailVerificationToken(
        psychologist_id=psychologist_id,
        email=email,
        token_hash=token_hash,
        expires_at=func.clock_timestamp() + timedelta(seconds=lifetime_seconds),
    )
    session.add(token)
    session.flush()
    session.refresh(token)
    return token


def get_email_verification(
    session: Session, token_hash: str, *, lock: bool = False
) -> EmailVerificationToken | None:
    statement = select(EmailVerificationToken).where(
        EmailVerificationToken.token_hash == token_hash
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def get_email_verification_by_id(
    session: Session, token_id: UUID, *, lock: bool = False
) -> EmailVerificationToken | None:
    statement = select(EmailVerificationToken).where(EmailVerificationToken.id == token_id)
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def get_unconsumed_email_verifications(
    session: Session,
    psychologist_id: UUID,
    email: str,
    *,
    lock: bool = False,
) -> list[EmailVerificationToken]:
    statement = (
        select(EmailVerificationToken)
        .where(
            EmailVerificationToken.psychologist_id == psychologist_id,
            EmailVerificationToken.email == email,
            EmailVerificationToken.consumed_at.is_(None),
        )
        .order_by(EmailVerificationToken.id)
    )
    if lock:
        statement = statement.with_for_update()
    return list(session.scalars(statement))


def add_booking_grant(
    session: Session,
    psychologist_id: UUID,
    email: str,
    token_hash: str,
    lifetime_seconds: int,
) -> BookingVerificationGrant:
    grant = BookingVerificationGrant(
        psychologist_id=psychologist_id,
        email=email,
        token_hash=token_hash,
        expires_at=func.clock_timestamp() + timedelta(seconds=lifetime_seconds),
    )
    session.add(grant)
    session.flush()
    session.refresh(grant)
    return grant


def get_booking_grant(
    session: Session, token_hash: str, *, lock: bool = False
) -> BookingVerificationGrant | None:
    statement = select(BookingVerificationGrant).where(
        BookingVerificationGrant.token_hash == token_hash
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)
