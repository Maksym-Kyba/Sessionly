import dataclasses
import logging
from uuid import UUID

import pytest

from app.payments.api import (
    BookingConfirmationDecision,
    MockPaymentGateway,
    PaymentIdempotencyConflict,
    PaymentOutcome,
    PaymentRequest,
    PaymentStatus,
    process_booking_payment,
)

BOOKING_ID = UUID("00000000-0000-0000-0000-000000000001")


class FakeConfirmBooking:
    """Stands in for the future booking adapter and records every call."""

    def __init__(
        self,
        decision: BookingConfirmationDecision = BookingConfirmationDecision.CONFIRMED,
        error: Exception | None = None,
    ) -> None:
        self.decision = decision
        self.error = error
        self.calls: list[tuple[UUID, str]] = []

    def __call__(self, booking_id: UUID, payment_reference: str) -> BookingConfirmationDecision:
        self.calls.append((booking_id, payment_reference))
        if self.error is not None:
            raise self.error
        return self.decision


def _request(*, amount_minor: int = 120000, idempotency_key: str = "payment-key-1") -> PaymentRequest:
    return PaymentRequest(
        booking_id=BOOKING_ID,
        amount_minor=amount_minor,
        currency="UAH",
        idempotency_key=idempotency_key,
    )


def test_failed_payment_never_reaches_booking_confirmation():
    confirm = FakeConfirmBooking()

    settlement = process_booking_payment(
        MockPaymentGateway(PaymentOutcome.FAILED), _request(), confirm
    )

    assert settlement.status is PaymentStatus.FAILED
    assert settlement.provider == "mock"
    assert confirm.calls == []


def test_confirmed_booking_settles_payment_as_succeeded():
    confirm = FakeConfirmBooking(BookingConfirmationDecision.CONFIRMED)

    settlement = process_booking_payment(
        MockPaymentGateway(PaymentOutcome.SUCCEEDED), _request(), confirm
    )

    assert settlement.status is PaymentStatus.SUCCEEDED
    assert confirm.calls == [(BOOKING_ID, settlement.provider_reference)]


def test_unconfirmed_booking_after_successful_payment_requires_manual_review():
    confirm = FakeConfirmBooking(BookingConfirmationDecision.NOT_CONFIRMED)

    settlement = process_booking_payment(
        MockPaymentGateway(PaymentOutcome.SUCCEEDED), _request(), confirm
    )

    assert settlement.status is PaymentStatus.MANUAL_REVIEW
    assert len(confirm.calls) == 1


def test_already_confirmed_booking_settles_payment_as_succeeded():
    confirm = FakeConfirmBooking(BookingConfirmationDecision.ALREADY_CONFIRMED)

    settlement = process_booking_payment(
        MockPaymentGateway(PaymentOutcome.SUCCEEDED), _request(), confirm
    )

    assert settlement.status is PaymentStatus.SUCCEEDED


def test_duplicate_request_reuses_payment_reference_and_result():
    gateway = MockPaymentGateway(PaymentOutcome.SUCCEEDED)
    first_confirm = FakeConfirmBooking(BookingConfirmationDecision.CONFIRMED)
    repeated_confirm = FakeConfirmBooking(BookingConfirmationDecision.ALREADY_CONFIRMED)

    first = process_booking_payment(gateway, _request(), first_confirm)
    repeated = process_booking_payment(gateway, _request(), repeated_confirm)

    assert repeated == first
    assert repeated_confirm.calls == [(BOOKING_ID, first.provider_reference)]


def test_reused_key_for_different_request_conflicts_before_confirmation():
    gateway = MockPaymentGateway(PaymentOutcome.SUCCEEDED)
    process_booking_payment(gateway, _request(), FakeConfirmBooking())
    confirm = FakeConfirmBooking()

    with pytest.raises(PaymentIdempotencyConflict):
        process_booking_payment(gateway, _request(amount_minor=99999), confirm)

    assert confirm.calls == []


def test_booking_confirmation_error_propagates_unchanged():
    error = RuntimeError("booking unavailable")
    confirm = FakeConfirmBooking(error=error)

    with pytest.raises(RuntimeError) as raised:
        process_booking_payment(MockPaymentGateway(PaymentOutcome.SUCCEEDED), _request(), confirm)

    assert raised.value is error


def test_service_emits_no_log_records(caplog):
    caplog.set_level(logging.DEBUG)

    process_booking_payment(
        MockPaymentGateway(PaymentOutcome.SUCCEEDED), _request(), FakeConfirmBooking()
    )
    process_booking_payment(
        MockPaymentGateway(PaymentOutcome.FAILED), _request(), FakeConfirmBooking()
    )

    assert caplog.records == []


def test_settlement_is_immutable():
    settlement = process_booking_payment(
        MockPaymentGateway(PaymentOutcome.SUCCEEDED), _request(), FakeConfirmBooking()
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        settlement.status = PaymentStatus.FAILED  # type: ignore[misc]
