"""Payment coordination between the payment gateway and booking confirmation.

The service collects a payment through a gateway and, for a successful payment, asks the booking
side whether it accepts the payment. It never changes booking state and never checks hold expiry:
booking lifecycle transitions and the 15-minute hold validation belong to the booking module.

The booking confirmation is received as a function parameter, so this module does not import the
booking module. A small adapter will later connect `booking.api.confirm_held_booking` to
`ConfirmBooking`.

The four booking confirmation decisions match the booking module's agreed confirmation outcomes.
PROPOSED: payment status names and the provisional handling of NOT_CONFIRMABLE are review
material, not final requirements. Payments are not persisted yet; a `session` parameter and
durable records will be added with the payments table.
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
    """The booking module's answer to a successful payment.

    Values match the booking module's confirmation outcomes so that the future adapter can map them
    directly.
    """

    CONFIRMED = "CONFIRMED"
    ALREADY_CONFIRMED = "ALREADY_CONFIRMED"
    EXPIRED = "EXPIRED"
    NOT_CONFIRMABLE = "NOT_CONFIRMABLE"


class PaymentSettlementError(Exception):
    """A gateway outcome or booking decision is not one this service knows how to settle."""


class ConfirmBooking(Protocol):
    def __call__(self, booking_id: UUID, payment_reference: str) -> BookingConfirmationDecision:
        """Ask the booking side to accept a successful payment for a booking.

        The implementation, owned by the booking module, checks whether the hold is still active
        and whether a confirmed booking was confirmed by this same payment reference. Repeating
        the call with the same payment reference must be safe.
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
    BookingConfirmationDecision.EXPIRED: PaymentStatus.MANUAL_REVIEW,
    # PROPOSED, provisional: the money was collected but the booking will not be confirmed, so
    # the payment is kept for manual review rather than treated as succeeded or discarded. The
    # final policy for NOT_CONFIRMABLE requires team approval.
    BookingConfirmationDecision.NOT_CONFIRMABLE: PaymentStatus.MANUAL_REVIEW,
}


def process_booking_payment(
    gateway: PaymentGateway,
    request: PaymentRequest,
    confirm_booking: ConfirmBooking,
) -> PaymentSettlement:
    """Collect a payment and settle it against booking confirmation.

    Only a successful payment reaches booking confirmation; a failed payment never does, and an
    unknown outcome raises `PaymentSettlementError` without contacting booking. A successful
    payment that booking does not confirm requires manual review and is never treated as a
    confirmed booking.
    """
    result = gateway.process_payment(request)
    if result.outcome is PaymentOutcome.SUCCEEDED:
        decision = confirm_booking(request.booking_id, result.provider_reference)
        try:
            status = _STATUS_BY_DECISION[BookingConfirmationDecision(decision)]
        except ValueError as exc:
            raise PaymentSettlementError("Unknown booking confirmation decision") from exc
    elif result.outcome is PaymentOutcome.FAILED:
        status = PaymentStatus.FAILED
    else:
        raise PaymentSettlementError("Unknown payment outcome")
    return PaymentSettlement(
        status=status,
        provider=result.provider,
        provider_reference=result.provider_reference,
    )
