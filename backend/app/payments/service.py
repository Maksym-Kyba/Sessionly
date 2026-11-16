"""Payment coordination between the payment gateway and booking confirmation.

The service collects a payment through a gateway and, for a successful payment, asks the booking
side whether it accepts the payment. It never changes booking state and never checks hold expiry:
booking lifecycle transitions and the 15-minute hold validation belong to the booking module.

The booking confirmation is received as a function parameter, so this module does not import the
booking module. Once `booking.api` exists, a small adapter will connect it to `ConfirmBooking`.

PROPOSED: status and decision names below are review material, not final requirements. Payments
are not persisted yet; a `session` parameter and durable records will be added with the payments
table.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from app.payments.gateway import PaymentGateway, PaymentOutcome, PaymentRequest


class PaymentStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class BookingConfirmationDecision(StrEnum):
    """The answer the payments module needs from booking confirmation."""

    CONFIRMED = "confirmed"
    ALREADY_CONFIRMED = "already_confirmed"
    NOT_CONFIRMED = "not_confirmed"


class ConfirmBooking(Protocol):
    def __call__(self, booking_id: UUID, payment_reference: str) -> BookingConfirmationDecision:
        """Ask the booking side to accept a successful payment for a booking.

        The implementation, owned by the booking module, decides whether the hold is still active.
        Repeating the call with the same payment reference must be safe.
        """
        ...


@dataclass(frozen=True)
class PaymentSettlement:
    status: PaymentStatus
    provider: str
    provider_reference: str


_STATUS_BY_DECISION = {
    BookingConfirmationDecision.CONFIRMED: PaymentStatus.SUCCEEDED,
    BookingConfirmationDecision.ALREADY_CONFIRMED: PaymentStatus.SUCCEEDED,
    BookingConfirmationDecision.NOT_CONFIRMED: PaymentStatus.MANUAL_REVIEW,
}


def process_booking_payment(
    gateway: PaymentGateway,
    request: PaymentRequest,
    confirm_booking: ConfirmBooking,
) -> PaymentSettlement:
    """Collect a payment and settle it against booking confirmation.

    A failed payment never reaches booking confirmation. A successful payment that booking does
    not confirm, for example because the hold has expired, requires manual review and is never
    treated as a confirmed booking.
    """
    result = gateway.process_payment(request)
    if result.outcome is PaymentOutcome.FAILED:
        status = PaymentStatus.FAILED
    else:
        decision = BookingConfirmationDecision(
            confirm_booking(request.booking_id, result.provider_reference)
        )
        status = _STATUS_BY_DECISION[decision]
    return PaymentSettlement(
        status=status,
        provider=result.provider,
        provider_reference=result.provider_reference,
    )
