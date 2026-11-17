import dataclasses
import logging
from uuid import UUID, uuid4

import pytest

from app.payments.api import (
    BookingConfirmationDecision,
    MockPaymentGateway,
    PaymentIdempotencyConflict,
    PaymentOutcome,
    PaymentRequest,
    PaymentResult,
    PaymentSettlementError,
    PaymentStatus,
    process_booking_payment,
    shared_mock_gateway,
    status_for_decision,
)

BOOKING_ID = UUID("00000000-0000-0000-0000-000000000001")


class FakeConfirmBooking:
    """Stands in for the future booking adapter.

    It returns scripted decisions in order (repeating the last one) and records every call. It
    deliberately contains no booking logic.
    """

    def __init__(self, *decisions: object, error: Exception | None = None) -> None:
        self.decisions = decisions or (BookingConfirmationDecision.CONFIRMED,)
        self.error = error
        self.calls: list[tuple[UUID, str]] = []

    def __call__(self, booking_id: UUID, payment_reference: str) -> BookingConfirmationDecision:
        self.calls.append((booking_id, payment_reference))
        if self.error is not None:
            raise self.error
        index = min(len(self.calls), len(self.decisions)) - 1
        return self.decisions[index]  # type: ignore[return-value]


class StubGateway:
    """Returns a fixed gateway result, including outcomes the service does not know."""

    provider_name = "stub"

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome

    def process_payment(self, request: PaymentRequest) -> PaymentResult:
        return PaymentResult(
            provider=self.provider_name,
            provider_reference="stub_reference",
            outcome=self.outcome,  # type: ignore[arg-type]
        )


def _request(
    *, amount_minor: int = 120000, idempotency_key: str = "payment-key-1"
) -> PaymentRequest:
    return PaymentRequest(
        booking_id=BOOKING_ID,
        amount_minor=amount_minor,
        currency="UAH",
        idempotency_key=idempotency_key,
    )


def test_decision_values_match_booking_confirmation_outcomes():
    assert {decision.value for decision in BookingConfirmationDecision} == {
        "CONFIRMED",
        "ALREADY_CONFIRMED",
        "EXPIRED",
        "NOT_CONFIRMABLE",
    }


def test_failed_payment_never_reaches_booking_confirmation():
    confirm = FakeConfirmBooking()

    settlement = process_booking_payment(
        MockPaymentGateway(PaymentOutcome.FAILED), _request(), confirm
    )

    assert settlement.status is PaymentStatus.FAILED
    assert settlement.provider == "mock"
    assert confirm.calls == []


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (BookingConfirmationDecision.CONFIRMED, PaymentStatus.SUCCEEDED),
        (BookingConfirmationDecision.ALREADY_CONFIRMED, PaymentStatus.SUCCEEDED),
        (BookingConfirmationDecision.EXPIRED, PaymentStatus.MANUAL_REVIEW),
        (BookingConfirmationDecision.NOT_CONFIRMABLE, PaymentStatus.MANUAL_REVIEW),
    ],
    ids=["confirmed", "already-confirmed", "expired", "not-confirmable"],
)
def test_successful_payment_is_settled_by_booking_decision(decision, expected_status):
    confirm = FakeConfirmBooking(decision)

    settlement = process_booking_payment(
        MockPaymentGateway(PaymentOutcome.SUCCEEDED), _request(), confirm
    )

    assert settlement.status is expected_status
    assert confirm.calls == [(BOOKING_ID, settlement.provider_reference)]


@pytest.mark.parametrize("outcome", ["pending", None], ids=["pending", "none"])
def test_unknown_payment_outcome_raises_without_reaching_booking(outcome):
    confirm = FakeConfirmBooking()

    with pytest.raises(PaymentSettlementError):
        process_booking_payment(StubGateway(outcome), _request(), confirm)

    assert confirm.calls == []


@pytest.mark.parametrize(
    "decision", ["not_confirmed", "confirmed", None], ids=["legacy", "lowercase", "none"]
)
def test_unknown_booking_decision_raises(decision):
    confirm = FakeConfirmBooking(decision)

    with pytest.raises(PaymentSettlementError):
        process_booking_payment(MockPaymentGateway(PaymentOutcome.SUCCEEDED), _request(), confirm)

    assert len(confirm.calls) == 1


def test_duplicate_request_forwards_same_reference_and_reuses_result():
    gateway = MockPaymentGateway(PaymentOutcome.SUCCEEDED)
    confirm = FakeConfirmBooking(
        BookingConfirmationDecision.CONFIRMED, BookingConfirmationDecision.ALREADY_CONFIRMED
    )

    first = process_booking_payment(gateway, _request(), confirm)
    repeated = process_booking_payment(gateway, _request(), confirm)

    assert repeated == first
    assert confirm.calls == [
        (BOOKING_ID, first.provider_reference),
        (BOOKING_ID, first.provider_reference),
    ]


def test_different_payment_reference_is_not_treated_as_already_confirmed():
    """The reference identity check belongs to booking; payments forwards each reference as-is."""
    gateway = MockPaymentGateway(PaymentOutcome.SUCCEEDED)
    confirm = FakeConfirmBooking(
        BookingConfirmationDecision.CONFIRMED, BookingConfirmationDecision.NOT_CONFIRMABLE
    )

    first = process_booking_payment(gateway, _request(idempotency_key="key-a"), confirm)
    second = process_booking_payment(gateway, _request(idempotency_key="key-b"), confirm)

    assert first.provider_reference != second.provider_reference
    assert confirm.calls == [
        (BOOKING_ID, first.provider_reference),
        (BOOKING_ID, second.provider_reference),
    ]
    assert first.status is PaymentStatus.SUCCEEDED
    assert second.status is PaymentStatus.MANUAL_REVIEW


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


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ("CONFIRMED", PaymentStatus.SUCCEEDED),
        ("ALREADY_CONFIRMED", PaymentStatus.SUCCEEDED),
        ("EXPIRED", PaymentStatus.MANUAL_REVIEW),
        ("NOT_CONFIRMABLE", PaymentStatus.MANUAL_REVIEW),
    ],
)
def test_status_for_decision_accepts_booking_outcome_values(decision, expected_status):
    assert status_for_decision(decision) is expected_status


@pytest.mark.parametrize("decision", ["not_confirmed", "confirmed", None])
def test_status_for_decision_rejects_unknown_values(decision):
    with pytest.raises(PaymentSettlementError):
        status_for_decision(decision)


def test_pending_is_never_a_settlement_result():
    assert PaymentStatus.PENDING not in {
        status_for_decision(d) for d in BookingConfirmationDecision
    }


def test_shared_mock_gateways_keep_idempotency_across_calls():
    gateway = shared_mock_gateway(PaymentOutcome.SUCCEEDED)
    request = _request(idempotency_key=f"shared-{uuid4()}")

    assert shared_mock_gateway("succeeded") is gateway
    assert shared_mock_gateway(PaymentOutcome.FAILED) is not gateway
    assert gateway.process_payment(request) == shared_mock_gateway(
        PaymentOutcome.SUCCEEDED
    ).process_payment(request)
