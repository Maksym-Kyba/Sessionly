"""Provider-independent payment gateway interface.

The gateway reports only the outcome of a payment attempt. It never decides booking state: the
booking module owns every booking lifecycle transition, including HELD -> CONFIRMED.

PROPOSED: the interface is a single synchronous call that returns a final outcome. Real providers
usually involve a redirect and an asynchronous webhook; the interface will be extended once the
production provider is chosen.

Requests and results intentionally contain no client personal data and no provider credentials.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

# Temporary MVP assumption, not a final product rule: only UAH is supported, matching the
# availability module.
SUPPORTED_CURRENCY = "UAH"


class PaymentOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PaymentGatewayError(Exception):
    """Base class for payment gateway errors."""


class InvalidPaymentRequest(PaymentGatewayError, ValueError):
    """The payment request is malformed or unsupported."""


class PaymentIdempotencyConflict(PaymentGatewayError):
    """An idempotency key was reused for a different payment request."""


@dataclass(frozen=True)
class PaymentRequest:
    """A request to collect a payment for a booking.

    `booking_id` is an opaque reference; the payments module never reads booking tables.

    Temporary MVP assumption, not a final product rule: the amount must be positive. Free
    consultations may require a separate flow that does not use the gateway.
    """

    booking_id: UUID
    amount_minor: int
    currency: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.booking_id, UUID):
            raise InvalidPaymentRequest("booking_id must be a UUID")
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise InvalidPaymentRequest("amount_minor must be an integer number of minor units")
        if self.amount_minor <= 0:
            raise InvalidPaymentRequest("amount_minor must be positive")
        if self.currency != SUPPORTED_CURRENCY:
            raise InvalidPaymentRequest(f"Only {SUPPORTED_CURRENCY} is supported")
        if not isinstance(self.idempotency_key, str) or not self.idempotency_key.strip():
            raise InvalidPaymentRequest("idempotency_key must be a non-empty string")


@dataclass(frozen=True)
class PaymentResult:
    """The outcome reported by a payment gateway.

    No timestamp is included: which payment timestamp is authoritative at the hold-expiry boundary
    remains unresolved pending team approval.
    """

    provider: str
    provider_reference: str
    outcome: PaymentOutcome


@runtime_checkable
class PaymentGateway(Protocol):
    provider_name: str

    def process_payment(self, request: PaymentRequest) -> PaymentResult:
        """Process a payment and return its outcome.

        Repeating a request with the same idempotency key must not collect a second payment.
        """
        ...
