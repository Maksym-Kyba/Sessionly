import dataclasses
import logging
from uuid import UUID, uuid4

import pytest

from app.payments.api import (
    InvalidPaymentRequest,
    MockPaymentGateway,
    PaymentGateway,
    PaymentIdempotencyConflict,
    PaymentOutcome,
    PaymentRequest,
)


def _request(
    *,
    booking_id: UUID | None = None,
    amount_minor: int = 120000,
    currency: str = "UAH",
    idempotency_key: str = "payment-key-1",
) -> PaymentRequest:
    return PaymentRequest(
        booking_id=booking_id or UUID("00000000-0000-0000-0000-000000000001"),
        amount_minor=amount_minor,
        currency=currency,
        idempotency_key=idempotency_key,
    )


def test_successful_outcome():
    result = MockPaymentGateway(PaymentOutcome.SUCCEEDED).process_payment(_request())

    assert result.outcome is PaymentOutcome.SUCCEEDED
    assert result.provider == "mock"
    assert result.provider_reference.startswith("mock_")
    assert len(result.provider_reference) > len("mock_")


def test_failed_outcome():
    result = MockPaymentGateway(PaymentOutcome.FAILED).process_payment(_request())

    assert result.outcome is PaymentOutcome.FAILED
    assert result.provider == "mock"


def test_distinct_requests_receive_distinct_references():
    gateway = MockPaymentGateway(PaymentOutcome.SUCCEEDED)

    first = gateway.process_payment(_request(idempotency_key="key-a"))
    second = gateway.process_payment(_request(idempotency_key="key-b"))

    assert first.provider_reference != second.provider_reference


@pytest.mark.parametrize("outcome", [PaymentOutcome.SUCCEEDED, PaymentOutcome.FAILED])
def test_repeated_request_with_same_key_returns_same_result(outcome):
    gateway = MockPaymentGateway(outcome)

    first = gateway.process_payment(_request())
    repeated = gateway.process_payment(_request())

    assert repeated == first


@pytest.mark.parametrize(
    "changed",
    [
        {"amount_minor": 99999},
        {"booking_id": UUID("00000000-0000-0000-0000-000000000002")},
    ],
)
def test_reused_key_for_different_request_conflicts(changed):
    gateway = MockPaymentGateway(PaymentOutcome.SUCCEEDED)
    gateway.process_payment(_request())

    with pytest.raises(PaymentIdempotencyConflict):
        gateway.process_payment(_request(**changed))


@pytest.mark.parametrize(
    "invalid",
    [
        {"amount_minor": 0},
        {"amount_minor": -100},
        {"amount_minor": 100.0},
        {"amount_minor": True},
        {"currency": "USD"},
        {"currency": "uah"},
        {"idempotency_key": ""},
        {"idempotency_key": "   "},
    ],
)
def test_invalid_requests_are_rejected(invalid):
    with pytest.raises(InvalidPaymentRequest):
        _request(**invalid)


def test_non_uuid_booking_id_is_rejected():
    with pytest.raises(InvalidPaymentRequest):
        PaymentRequest(
            booking_id="book_789",  # type: ignore[arg-type]
            amount_minor=120000,
            currency="UAH",
            idempotency_key="payment-key-1",
        )


def test_mock_satisfies_gateway_interface():
    assert isinstance(MockPaymentGateway(PaymentOutcome.SUCCEEDED), PaymentGateway)


def test_gateway_emits_no_log_records(caplog):
    caplog.set_level(logging.DEBUG)
    gateway = MockPaymentGateway(PaymentOutcome.SUCCEEDED)

    gateway.process_payment(_request(booking_id=uuid4()))

    assert caplog.records == []


def test_request_and_result_are_immutable():
    request = _request()
    result = MockPaymentGateway(PaymentOutcome.SUCCEEDED).process_payment(request)

    with pytest.raises(dataclasses.FrozenInstanceError):
        request.amount_minor = 1  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.outcome = PaymentOutcome.FAILED  # type: ignore[misc]
