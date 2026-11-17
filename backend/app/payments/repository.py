from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.payments.models import Payment


def lock_booking_payments(session: Session, booking_id: UUID) -> None:
    """Serialize payment attempts for one booking until the current transaction ends.

    This is a PostgreSQL advisory lock owned by the payments module; it does not lock or touch
    booking's tables.
    """
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"sessionly.payments.booking:{booking_id}"},
    )


def get_by_idempotency_key_hash(session: Session, key_hash: str) -> Payment | None:
    return session.scalar(select(Payment).where(Payment.idempotency_key_hash == key_hash))


def insert_pending(
    session: Session,
    *,
    booking_id: UUID,
    key_hash: str,
    request_hash: str,
    provider: str,
    amount_minor: int,
    currency: str,
) -> UUID | None:
    """Insert a pending payment; return None if the idempotency key is already recorded.

    A violation of any other unique index (for example, another pending payment for the same
    booking) raises IntegrityError.
    """
    return session.scalar(
        insert(Payment)
        .values(
            booking_id=booking_id,
            idempotency_key_hash=key_hash,
            request_hash=request_hash,
            provider=provider,
            amount_minor=amount_minor,
            currency=currency,
            status="pending",
        )
        .on_conflict_do_nothing(index_elements=[Payment.idempotency_key_hash])
        .returning(Payment.id)
    )


def get_for_update(session: Session, payment_id: UUID) -> Payment | None:
    return session.scalar(select(Payment).where(Payment.id == payment_id).with_for_update())
