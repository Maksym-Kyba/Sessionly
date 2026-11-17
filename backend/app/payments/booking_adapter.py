"""Adapter between the payments module and the booking module's public API.

This is the only payments file that imports the booking module. Booking's `PaymentResult` is
imported as `BookingPaymentResult` so that it is never confused with the gateway's `PaymentResult`.
Booking alone decides whether a hold is still active and performs every booking transition.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.booking import api as booking_api
from app.booking.api import PayableBooking
from app.booking.api import PaymentResult as BookingPaymentResult

__all__ = [
    "BookingPaymentResult",
    "PayableBooking",
    "client_can_access_booking",
    "confirm_booking",
    "payable_booking",
]


def client_can_access_booking(session: Session, booking_id: UUID, client_access_token: str) -> bool:
    """Check the client's bearer token through booking's own access-token verification."""
    return booking_api.get_client_booking(session, booking_id, client_access_token) is not None


def payable_booking(session: Session, booking_id: UUID) -> PayableBooking | None:
    """Return booking's amount and currency snapshot while the booking is still payable."""
    return booking_api.get_payable_booking(session, booking_id)


def confirm_booking(session: Session, booking_id: UUID, payment_reference: str) -> str:
    """Report a successful payment to booking and return booking's confirmation outcome.

    The outcome value is converted to `BookingConfirmationDecision` by the payments service, which
    rejects any value outside the agreed contract.
    """
    return booking_api.confirm_held_booking(
        session,
        booking_id,
        BookingPaymentResult(payment_reference=payment_reference, succeeded=True),
    )
