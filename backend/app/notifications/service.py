import hashlib
import hmac
import secrets
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from app.accounts import api as accounts_api
from app.core.config import settings
from app.notifications import repository
from app.notifications.email_sender import EmailDeliveryUnavailable, EmailSender
from app.notifications.models import BookingVerificationGrant, EmailVerificationToken
from app.notifications.schemas import VerificationRequest


class InvalidVerificationToken(Exception):
    """Raised for invalid, expired, consumed, or out-of-scope client tokens."""


class VerificationRateLimited(Exception):
    """Raised when the public verification-consumption limit is exceeded."""


def normalize_email(value: str) -> str:
    return value.strip().lower()


def _token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _privacy_hash(value: str) -> str:
    return hmac.new(
        settings.client_verification_secret_key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _verification_url(raw_token: str) -> str:
    parts = urlsplit(settings.client_verification_link_base_url)
    # Fragments are not sent to frontend servers or included in HTTP access logs.
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, f"token={raw_token}"))


def request_email_verification(
    session: Session,
    data: VerificationRequest,
    sender: EmailSender,
) -> None:
    email = normalize_email(data.email)
    with session.begin():
        psychologist = accounts_api.psychologist_by_public_id(session, data.psychologist_public_id)
        if psychologist is None:
            return
        email_key = _privacy_hash(f"verification-email:{psychologist.id}:{email}")
        psychologist_key = _privacy_hash(f"verification-psychologist:{psychologist.id}")
        psychologist_count = repository.increment_rate_limit(session, psychologist_key)
        repository.prune_expired_public_state(session)
        if psychologist_count <= settings.client_verification_psychologist_limit_per_hour:
            email_count = repository.increment_rate_limit(session, email_key)
        else:
            email_count = settings.client_verification_email_limit_per_hour + 1
        psychologist_id = psychologist.id
    if (
        email_count > settings.client_verification_email_limit_per_hour
        or psychologist_count > settings.client_verification_psychologist_limit_per_hour
    ):
        return

    raw_token = secrets.token_urlsafe(32)
    with session.begin():
        # Serialize active-link replacement for a psychologist. Without this lock,
        # two concurrent requests can each insert a token and fail to see the
        # other's uncommitted row while deleting older links.
        psychologist = accounts_api.psychologist_by_id(session, psychologist_id, lock=True)
        if psychologist is None:
            return
        token = repository.add_email_verification(
            session,
            psychologist_id,
            email,
            _token_hash(raw_token),
            settings.client_verification_ttl_seconds,
        )
        # Keep only the newest active link for one email/psychologist pair.
        session.execute(
            delete(EmailVerificationToken).where(
                EmailVerificationToken.psychologist_id == psychologist_id,
                EmailVerificationToken.email == email,
                EmailVerificationToken.id != token.id,
                EmailVerificationToken.consumed_at.is_(None),
            )
        )
        try:
            sender.send_verification(email, _verification_url(raw_token))
        except Exception:
            raise EmailDeliveryUnavailable("Email delivery failed") from None


def consume_email_verification(session: Session, raw_token: str) -> tuple[str, datetime, str]:
    with session.begin():
        key_hash = _privacy_hash("verification-consume:global")
        count = repository.increment_rate_limit(session, key_hash, window_seconds=60)
        limited = count > settings.client_verification_consume_limit_per_minute
    if limited:
        raise VerificationRateLimited
    with session.begin():
        token = repository.get_email_verification(session, _token_hash(raw_token), lock=True)
        now = session.scalar(func.clock_timestamp())
        if token is None or token.consumed_at is not None or now is None or token.expires_at <= now:
            raise InvalidVerificationToken
        psychologist = accounts_api.psychologist_by_id(session, token.psychologist_id)
        if psychologist is None:
            raise InvalidVerificationToken
        token.consumed_at = now
        raw_grant = secrets.token_urlsafe(32)
        grant = repository.add_booking_grant(
            session,
            token.psychologist_id,
            token.email,
            _token_hash(raw_grant),
            settings.client_verification_ttl_seconds,
        )
        return raw_grant, grant.expires_at, psychologist.public_id


def consume_booking_verification(
    session: Session, raw_token: str, psychologist_id: UUID
) -> tuple[str, UUID]:
    grant: BookingVerificationGrant | None = repository.get_booking_grant(
        session, _token_hash(raw_token), lock=True
    )
    now = session.scalar(func.clock_timestamp())
    if (
        grant is None
        or grant.consumed_at is not None
        or grant.expires_at <= now
        or grant.psychologist_id != psychologist_id
    ):
        raise InvalidVerificationToken
    grant.consumed_at = now
    return grant.email, grant.psychologist_id


def validate_consumed_booking_verification(
    session: Session, raw_token: str, psychologist_id: UUID
) -> tuple[str, UUID]:
    grant: BookingVerificationGrant | None = repository.get_booking_grant(
        session, _token_hash(raw_token), lock=True
    )
    now = session.scalar(func.clock_timestamp())
    if (
        grant is None
        or grant.consumed_at is None
        or now is None
        or grant.expires_at <= now
        or grant.psychologist_id != psychologist_id
    ):
        raise InvalidVerificationToken
    return grant.email, grant.psychologist_id


def verification_grant_for_recovery(
    session: Session, raw_token: str, psychologist_id: UUID
) -> tuple[str, UUID]:
    return consume_booking_verification(session, raw_token, psychologist_id)
