from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.accounts.dependencies import get_optional_current_psychologist_id
from app.booking import api
from app.booking.schemas import (
    BookingAccessTokenRead,
    BookingAccessTokenRecoveryRequest,
    ClientBookingRead,
    PublicBookingCreateRequest,
    PublicBookingCreatedRead,
)
from app.core.database import get_db

router = APIRouter(prefix="/api/v1", tags=["booking"])


@router.post("/bookings", response_model=PublicBookingCreatedRead, status_code=201)
def create_public_booking(
    data: PublicBookingCreateRequest,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    session: Session = Depends(get_db),
) -> PublicBookingCreatedRead:
    try:
        booking = api.create_verified_hold(
            session,
            data.slot_id,
            data.booking_verification_token,
            idempotency_key,
        )
    except api.InvalidVerificationToken as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking verification is invalid or expired",
        ) from exc
    except api.IdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was already used for a different request",
        ) from exc
    except api.BookingConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Availability slot is no longer available",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if booking.idempotent_replay:
        response.status_code = status.HTTP_200_OK
    response.headers["Cache-Control"] = "no-store"
    return PublicBookingCreatedRead(
        id=booking.id,
        status=booking.status,
        slot_id=booking.availability_slot_id,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        session_duration_minutes=booking.session_duration_minutes,
        price_minor=booking.price_minor,
        currency=booking.currency,
        created_at=booking.created_at,
        hold_expires_at=booking.hold_expires_at,
        client_access_token=booking.client_access_token,
        client_access_token_expires_at=booking.access_token_expires_at,
        idempotent_replay=booking.idempotent_replay,
    )


@router.post(
    "/bookings/{booking_id}/access-token",
    response_model=BookingAccessTokenRead,
)
def recover_access_token(
    booking_id: UUID,
    data: BookingAccessTokenRecoveryRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> BookingAccessTokenRead:
    try:
        recovered = api.recover_client_access_token(
            session, booking_id, data.booking_verification_token
        )
    except api.InvalidVerificationToken as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Booking verification is invalid or expired",
        ) from exc
    if recovered is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    raw_token, expires_at = recovered
    response.headers["Cache-Control"] = "no-store"
    return BookingAccessTokenRead(client_access_token=raw_token, expires_at=expires_at)


@router.get("/bookings/{booking_id}", response_model=ClientBookingRead)
def get_booking(
    booking_id: UUID,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    psychologist_id: UUID | None = Depends(get_optional_current_psychologist_id),
) -> ClientBookingRead:
    response.headers["Cache-Control"] = "no-store"
    authorization = request.headers.get("authorization")
    if authorization is not None:
        scheme, separator, token = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not token:
            raise HTTPException(status_code=401, detail="Booking access is required")
        booking = api.get_client_booking(session, booking_id, token)
    else:
        if psychologist_id is None:
            raise HTTPException(status_code=401, detail="Booking access is required")
        booking = api.get_psychologist_booking(session, booking_id, psychologist_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found")
    return ClientBookingRead(
        id=booking.id,
        status=booking.status,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        session_duration_minutes=booking.session_duration_minutes,
        price_minor=booking.price_minor,
        currency=booking.currency,
        created_at=booking.created_at,
        hold_expires_at=booking.hold_expires_at,
    )
