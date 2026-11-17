"""Development mock payment gateway.

The mock performs no network calls, requires no credentials and executes no real transactions.
Idempotency is tracked in memory for the lifetime of one gateway instance only; durable
idempotency belongs to future payment records.
"""

import secrets
from threading import Lock

from app.payments.gateway import (
    PaymentIdempotencyConflict,
    PaymentOutcome,
    PaymentRequest,
    PaymentResult,
)


class MockPaymentGateway:
    provider_name = "mock"

    def __init__(self, outcome: PaymentOutcome) -> None:
        self._outcome = PaymentOutcome(outcome)
        self._processed: dict[str, tuple[PaymentRequest, PaymentResult]] = {}
        self._lock = Lock()

    def process_payment(self, request: PaymentRequest) -> PaymentResult:
        with self._lock:
            previous = self._processed.get(request.idempotency_key)
            if previous is not None:
                previous_request, previous_result = previous
                if previous_request != request:
                    raise PaymentIdempotencyConflict(
                        "Idempotency key was already used for a different payment request"
                    )
                return previous_result

            result = PaymentResult(
                provider=self.provider_name,
                provider_reference=f"mock_{secrets.token_hex(16)}",
                outcome=self._outcome,
            )
            self._processed[request.idempotency_key] = (request, result)
            return result
