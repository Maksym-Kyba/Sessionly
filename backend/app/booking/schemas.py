from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class BookingConflict(Exception):
    """Raised when a requested availability interval cannot be reserved."""


class ConfirmationOutcome(StrEnum):
    CONFIRMED = "CONFIRMED"
    ALREADY_CONFIRMED = "ALREADY_CONFIRMED"
    EXPIRED = "EXPIRED"
    NOT_CONFIRMABLE = "NOT_CONFIRMABLE"


@dataclass(frozen=True)
class BookingHold:
    id: UUID
    availability_slot_id: UUID
    psychologist_id: UUID
    starts_at: datetime
    ends_at: datetime
    session_duration_minutes: int
    price_minor: int
    currency: str
    status: str
    created_at: datetime
    hold_expires_at: datetime


@dataclass(frozen=True)
class PayableBooking:
    booking_id: UUID
    amount_minor: int
    currency: str
    hold_expires_at: datetime


@dataclass(frozen=True)
class PaymentResult:
    payment_reference: str | None
    succeeded: bool


@dataclass(frozen=True)
class PublicBookingCreation:
    id: UUID
    availability_slot_id: UUID
    psychologist_id: UUID
    starts_at: datetime
    ends_at: datetime
    session_duration_minutes: int
    price_minor: int
    currency: str
    status: str
    created_at: datetime
    hold_expires_at: datetime
    client_access_token: str | None
    access_token_expires_at: datetime | None
    idempotent_replay: bool


@dataclass(frozen=True)
class ClientBooking:
    id: UUID
    status: str
    starts_at: datetime
    ends_at: datetime
    session_duration_minutes: int
    price_minor: int
    currency: str
    hold_expires_at: datetime
    created_at: datetime


class PublicBookingCreateRequest(BaseModel):
    slot_id: UUID
    booking_verification_token: str = Field(min_length=32, max_length=256)


class PublicBookingCreatedRead(BaseModel):
    id: UUID
    status: str
    slot_id: UUID
    starts_at: datetime
    ends_at: datetime
    session_duration_minutes: int
    price_minor: int
    currency: str
    created_at: datetime
    hold_expires_at: datetime
    client_access_token: str | None
    client_access_token_expires_at: datetime | None
    idempotent_replay: bool
    payment_stage: str = "awaiting_payment_integration"


class BookingAccessTokenRecoveryRequest(BaseModel):
    booking_verification_token: str = Field(min_length=32, max_length=256)


class BookingAccessTokenRead(BaseModel):
    client_access_token: str
    expires_at: datetime


class ClientBookingRead(BaseModel):
    id: UUID
    status: str
    starts_at: datetime
    ends_at: datetime
    session_duration_minutes: int
    price_minor: int
    currency: str
    created_at: datetime
    hold_expires_at: datetime
