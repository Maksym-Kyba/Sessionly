from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.notifications import api
from app.notifications.email_sender import EmailDeliveryUnavailable, EmailSender
from app.notifications.schemas import (
    VerificationAccepted,
    VerificationConsumeRequest,
    VerificationGrantRead,
    VerificationRequest,
)

router = APIRouter(prefix="/api/v1", tags=["client verification"])


def get_email_sender(request: Request) -> EmailSender:
    return request.app.state.email_sender


@router.post(
    "/email-verifications",
    response_model=VerificationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_verification(
    data: VerificationRequest,
    response: Response,
    session: Session = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
) -> VerificationAccepted:
    try:
        api.request_email_verification(session, data, sender)
    except EmailDeliveryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email delivery is temporarily unavailable",
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    return VerificationAccepted()


@router.post("/email-verifications/consume", response_model=VerificationGrantRead)
def consume_verification(
    data: VerificationConsumeRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> VerificationGrantRead:
    try:
        raw_grant, expires_at = api.consume_email_verification(session, data.token)
    except api.VerificationRateLimited as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Verification requests are temporarily rate limited",
            headers={"Retry-After": "60"},
        ) from exc
    except api.InvalidVerificationToken as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link is invalid or expired",
        ) from exc
    response.headers["Cache-Control"] = "no-store"
    return VerificationGrantRead(
        booking_verification_token=raw_grant,
        expires_at=expires_at,
    )
