from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.payments import service
from app.payments.gateway import InvalidPaymentRequest, PaymentIdempotencyConflict, PaymentOutcome
from app.payments.mock_gateway import shared_mock_gateway
from app.payments.schemas import MockPaymentRequest, PaymentRead

router = APIRouter(prefix="/api/v1", tags=["payments"])

_OUTCOME_BY_RESULT = {"success": PaymentOutcome.SUCCEEDED, "failure": PaymentOutcome.FAILED}


def require_mock_payments_enabled() -> None:
    """Hide the mock endpoint unless mock payments are explicitly or implicitly enabled."""
    if not settings.mock_payments_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


def client_access_token(request: Request) -> str:
    """Read the booking's client bearer token, following the booking routes' convention."""
    authorization = request.headers.get("authorization")
    scheme, separator, token = (authorization or "").partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Booking access is required")
    return token


@router.post(
    "/bookings/{booking_id}/payments/mock",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_mock_payments_enabled)],
    # Development-only simulation: not part of the public API documentation.
    include_in_schema=False,
)
def create_mock_payment(
    booking_id: UUID,
    data: MockPaymentRequest,
    response: Response,
    access_token: str = Depends(client_access_token),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    session: Session = Depends(get_db),
) -> PaymentRead:
    """Development only: simulate a payment for a held booking without moving real money."""
    response.headers["Cache-Control"] = "no-store"
    try:
        payment = service.pay_booking_for_client(
            session,
            booking_id,
            access_token,
            idempotency_key,
            shared_mock_gateway(_OUTCOME_BY_RESULT[data.result]),
            request_details=data.result,
        )
    except service.BookingAccessDenied as exc:
        raise HTTPException(status_code=404, detail="Booking not found") from exc
    except PaymentIdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was already used for a different request",
        ) from exc
    except service.PaymentInProgress as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another payment for this booking is still being processed",
        ) from exc
    except service.PaymentRequiresManualReview as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A previous payment for this booking requires manual review",
        ) from exc
    except service.BookingNotPayable as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Booking is not available for payment"
        ) from exc
    except InvalidPaymentRequest as exc:
        raise HTTPException(status_code=422, detail="Booking cannot be paid") from exc
    if payment.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    return PaymentRead(
        payment_id=payment.payment_id,
        booking_id=payment.booking_id,
        payment_status=payment.status.value,
        booking_decision=(
            None if payment.booking_decision is None else payment.booking_decision.value
        ),
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        provider=payment.provider,
        provider_reference=payment.provider_reference,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        idempotent_replay=payment.idempotent_replay,
    )
