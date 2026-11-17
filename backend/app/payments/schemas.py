from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class MockPaymentRequest(BaseModel):
    """Simulated payment outcome.

    Unknown fields are rejected, so a client cannot supply an amount, currency or provider data;
    the payable amount always comes from the booking snapshot.
    """

    model_config = ConfigDict(extra="forbid")

    result: Literal["success", "failure"]


class PaymentRead(BaseModel):
    payment_id: UUID
    booking_id: UUID
    payment_status: Literal["pending", "succeeded", "failed", "manual_review"]
    booking_decision: Literal["CONFIRMED", "ALREADY_CONFIRMED", "EXPIRED", "NOT_CONFIRMABLE"] | None
    amount_minor: int
    currency: str
    provider: str
    provider_reference: str | None
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool
