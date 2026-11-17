"""Public interface for verified client identity and email delivery."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.notifications import service
from app.notifications.email_sender import EmailSender
from app.notifications.schemas import VerificationRequest


InvalidVerificationToken = service.InvalidVerificationToken
VerificationRateLimited = service.VerificationRateLimited


def request_email_verification(
    session: Session, data: VerificationRequest, sender: EmailSender
) -> None:
    service.request_email_verification(session, data, sender)


def consume_email_verification(session: Session, raw_token: str):
    return service.consume_email_verification(session, raw_token)


def consume_booking_verification(
    session: Session, raw_token: str, psychologist_id: UUID
) -> tuple[str, UUID]:
    return service.consume_booking_verification(session, raw_token, psychologist_id)


def validate_consumed_booking_verification(
    session: Session, raw_token: str, psychologist_id: UUID
) -> tuple[str, UUID]:
    return service.validate_consumed_booking_verification(session, raw_token, psychologist_id)
