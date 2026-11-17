"""PostgreSQL tests for payment persistence and integration with the real booking module."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event, Lock
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.availability.models import AvailabilitySlot
from app.booking import api as booking_api
from app.booking.models import Booking, BookingStatus
from app.core.config import settings
from app.payments import booking_adapter
from app.payments.api import (
    BookingConfirmationDecision,
    BookingNotPayable,
    InvalidPaymentRequest,
    MockPaymentGateway,
    PaymentIdempotencyConflict,
    PaymentInProgress,
    PaymentOutcome,
    PaymentRequest,
    PaymentRequiresManualReview,
    PaymentResult,
    PaymentStatus,
    pay_booking,
)
from app.payments.models import Payment

BACKEND_ROOT = Path(__file__).resolve().parents[1]
BARRIER_TIMEOUT_SECONDS = 120


class RecordingGateway:
    """Wraps a gateway, counts charges, and can run a hook or fail before returning."""

    def __init__(self, gateway, *, before_return=None, error: Exception | None = None) -> None:
        self.gateway = gateway
        self.provider_name = gateway.provider_name
        self.before_return = before_return
        self.error = error
        self.calls: list[PaymentRequest] = []
        self._lock = Lock()

    def process_payment(self, request: PaymentRequest) -> PaymentResult:
        with self._lock:
            self.calls.append(request)
        if self.error is not None:
            raise self.error
        result = self.gateway.process_payment(request)
        if self.before_return is not None:
            self.before_return(result)
        return result


class FixedReferenceGateway:
    """Always succeeds with one fixed reference, like a provider replaying a known payment."""

    provider_name = "mock"

    def __init__(self, reference: str) -> None:
        self.reference = reference

    def process_payment(self, request: PaymentRequest) -> PaymentResult:
        return PaymentResult(
            provider=self.provider_name,
            provider_reference=self.reference,
            outcome=PaymentOutcome.SUCCEEDED,
        )


def succeeding() -> RecordingGateway:
    return RecordingGateway(MockPaymentGateway(PaymentOutcome.SUCCEEDED))


def failing() -> RecordingGateway:
    return RecordingGateway(MockPaymentGateway(PaymentOutcome.FAILED))


def create_held_booking(database_engine, psychologist_id, *, offset_minutes=0, price_minor=120000):
    starts_at = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(
        days=2, minutes=offset_minutes
    )
    with Session(database_engine) as session, session.begin():
        slot = AvailabilitySlot(
            psychologist_id=psychologist_id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=50),
            price_minor=price_minor,
            currency="UAH",
            state="published",
        )
        session.add(slot)
        session.flush()
        slot_id = slot.id
    with Session(database_engine) as session:
        return booking_api.create_hold(session, slot_id).id


def expire_hold(database_engine, booking_id) -> None:
    with Session(database_engine) as session, session.begin():
        session.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(hold_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )


def booking_record(database_engine, booking_id) -> Booking:
    with Session(database_engine) as session:
        booking = session.get(Booking, booking_id)
        assert booking is not None
        session.expunge(booking)
        return booking


def payment_rows(database_engine, booking_id=None) -> list[Payment]:
    with Session(database_engine) as session:
        statement = select(Payment).order_by(Payment.created_at)
        if booking_id is not None:
            statement = statement.where(Payment.booking_id == booking_id)
        rows = list(session.scalars(statement))
        for row in rows:
            session.expunge(row)
        return rows


def pay(database_engine, booking_id, key, gateway, details="success"):
    with Session(database_engine) as session:
        return pay_booking(session, booking_id, key, gateway, request_details=details)


# Migration and model constraints


def test_migration_creates_payments_table_with_constraints(database_engine):
    inspector = inspect(database_engine)
    columns = {column["name"] for column in inspector.get_columns("payments")}
    assert columns == {
        "id",
        "booking_id",
        "idempotency_key_hash",
        "request_hash",
        "provider",
        "provider_reference",
        "amount_minor",
        "currency",
        "status",
        "booking_decision",
        "created_at",
        "updated_at",
    }
    indexes = {index["name"]: index for index in inspector.get_indexes("payments")}
    for name in (
        "uq_payments_idempotency_key_hash",
        "uq_payments_provider_reference",
        "uq_payments_one_pending_per_booking",
        "uq_payments_one_succeeded_per_booking",
    ):
        assert indexes[name]["unique"]
    foreign_keys = inspector.get_foreign_keys("payments")
    assert [(key["referred_table"], key["constrained_columns"]) for key in foreign_keys] == [
        ("bookings", ["booking_id"])
    ]
    checks = {check["name"] for check in inspector.get_check_constraints("payments")}
    assert {
        "ck_payments_amount",
        "ck_payments_currency",
        "ck_payments_status",
        "ck_payments_booking_decision",
        "ck_payments_succeeded_requires_confirmation",
        "ck_payments_manual_review_requires_reference",
        "ck_payments_undecided_without_booking_decision",
    } <= checks


def test_migration_downgrade_and_upgrade_round_trip(database_engine, isolated_database_url):
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    original_database_url = settings.database_url
    settings.database_url = isolated_database_url.render_as_string(hide_password=False)
    try:
        command.downgrade(alembic_config, "20261117_0005")
        assert "payments" not in inspect(database_engine).get_table_names()
        command.upgrade(alembic_config, "head")
    finally:
        settings.database_url = original_database_url
    assert "payments" in inspect(database_engine).get_table_names()


def _payment_values(booking_id, **overrides) -> dict:
    values = {
        "booking_id": booking_id,
        "idempotency_key_hash": uuid4().hex * 2,
        "request_hash": "0" * 64,
        "provider": "mock",
        "provider_reference": None,
        "amount_minor": 120000,
        "currency": "UAH",
        "status": "pending",
        "booking_decision": None,
    }
    values.update(overrides)
    return values


def _insert(database_engine, **values) -> None:
    with Session(database_engine) as session, session.begin():
        session.add(Payment(**values))


@pytest.mark.parametrize(
    "overrides",
    [
        {"amount_minor": 0},
        {"amount_minor": -1},
        {"currency": "USD"},
        {"status": "paid"},
        {"booking_decision": "MAYBE", "status": "manual_review", "provider_reference": "r-1"},
        {"status": "succeeded", "provider_reference": "r-1"},
        {"status": "succeeded", "provider_reference": "r-1", "booking_decision": "EXPIRED"},
        {"status": "succeeded", "booking_decision": "CONFIRMED"},
        {"status": "manual_review", "booking_decision": "EXPIRED"},
        {"status": "failed", "provider_reference": "r-1", "booking_decision": "CONFIRMED"},
        {"status": "pending", "booking_decision": "CONFIRMED"},
    ],
    ids=[
        "zero-amount",
        "negative-amount",
        "non-uah",
        "unknown-status",
        "unknown-decision",
        "succeeded-without-decision",
        "succeeded-after-expiry",
        "succeeded-without-reference",
        "manual-review-without-reference",
        "failed-with-decision",
        "pending-with-decision",
    ],
)
def test_check_constraints_reject_invalid_rows(database_engine, psychologist, overrides):
    booking_id = create_held_booking(database_engine, psychologist.id)

    with pytest.raises(IntegrityError):
        _insert(database_engine, **_payment_values(booking_id, **overrides))


def test_unique_idempotency_key_and_provider_reference(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)
    _insert(
        database_engine,
        **_payment_values(
            booking_id, idempotency_key_hash="a" * 64, status="failed", provider_reference="ref-1"
        ),
    )

    with pytest.raises(IntegrityError):
        _insert(database_engine, **_payment_values(booking_id, idempotency_key_hash="a" * 64))
    with pytest.raises(IntegrityError):
        _insert(
            database_engine,
            **_payment_values(booking_id, status="failed", provider_reference="ref-1"),
        )


def test_at_most_one_pending_and_one_succeeded_payment_per_booking(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)
    _insert(database_engine, **_payment_values(booking_id))
    succeeded = {"status": "succeeded", "booking_decision": "CONFIRMED"}
    _insert(database_engine, **_payment_values(booking_id, provider_reference="r-1", **succeeded))

    with pytest.raises(IntegrityError):
        _insert(database_engine, **_payment_values(booking_id))
    with pytest.raises(IntegrityError):
        _insert(
            database_engine, **_payment_values(booking_id, provider_reference="r-2", **succeeded)
        )


def test_payment_requires_an_existing_booking(database_engine):
    with pytest.raises(IntegrityError):
        _insert(database_engine, **_payment_values(uuid4()))


# Booking integration


def test_successful_payment_confirms_booking_with_its_reference(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)
    gateway = succeeding()

    payment = pay(database_engine, booking_id, "key-success-0001", gateway)

    assert payment.status is PaymentStatus.SUCCEEDED
    assert payment.booking_decision is BookingConfirmationDecision.CONFIRMED
    assert payment.idempotent_replay is False
    assert payment.provider == "mock"
    booking = booking_record(database_engine, booking_id)
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.payment_reference == payment.provider_reference
    [row] = payment_rows(database_engine, booking_id)
    assert row.status == "succeeded"
    assert row.idempotency_key_hash != "key-success-0001"
    assert len(row.idempotency_key_hash) == 64
    assert len(gateway.calls) == 1


def test_amount_and_currency_come_from_booking_snapshot(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id, price_minor=155000)
    gateway = succeeding()

    payment = pay(database_engine, booking_id, "key-snapshot-0001", gateway)

    assert (payment.amount_minor, payment.currency) == (155000, "UAH")
    assert gateway.calls[0].amount_minor == 155000
    assert gateway.calls[0].idempotency_key == str(payment.payment_id)


def test_failed_payment_leaves_booking_held_and_allows_a_new_attempt(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)

    failed = pay(database_engine, booking_id, "key-failure-0001", failing(), "failure")
    assert failed.status is PaymentStatus.FAILED
    assert failed.booking_decision is None
    assert booking_record(database_engine, booking_id).status == BookingStatus.HELD

    retried = pay(database_engine, booking_id, "key-failure-0002", succeeding())
    assert retried.status is PaymentStatus.SUCCEEDED
    assert booking_record(database_engine, booking_id).status == BookingStatus.CONFIRMED
    assert [row.status for row in payment_rows(database_engine, booking_id)] == [
        "failed",
        "succeeded",
    ]


def test_hold_expiring_during_payment_goes_to_manual_review(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)
    gateway = RecordingGateway(
        MockPaymentGateway(PaymentOutcome.SUCCEEDED),
        before_return=lambda result: expire_hold(database_engine, booking_id),
    )

    payment = pay(database_engine, booking_id, "key-expired-0001", gateway)

    assert payment.status is PaymentStatus.MANUAL_REVIEW
    assert payment.booking_decision is BookingConfirmationDecision.EXPIRED
    assert payment.provider_reference is not None
    booking = booking_record(database_engine, booking_id)
    assert booking.status == BookingStatus.EXPIRED
    assert booking.payment_reference is None


def test_booking_confirmed_by_another_payment_is_not_confirmable(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)

    def confirm_elsewhere(result):
        with Session(database_engine) as session:
            outcome = booking_api.confirm_held_booking(
                session,
                booking_id,
                booking_adapter.BookingPaymentResult(
                    payment_reference="another-provider-payment", succeeded=True
                ),
            )
        assert outcome == "CONFIRMED"

    gateway = RecordingGateway(
        MockPaymentGateway(PaymentOutcome.SUCCEEDED), before_return=confirm_elsewhere
    )

    payment = pay(database_engine, booking_id, "key-other-ref-0001", gateway)

    assert payment.status is PaymentStatus.MANUAL_REVIEW
    assert payment.booking_decision is BookingConfirmationDecision.NOT_CONFIRMABLE
    booking = booking_record(database_engine, booking_id)
    assert booking.status == BookingStatus.CONFIRMED
    assert booking.payment_reference == "another-provider-payment"


def test_already_confirmed_with_the_same_reference_settles_as_succeeded(
    database_engine, psychologist
):
    """Booking was confirmed with this payment's own reference while the charge was in flight."""
    booking_id = create_held_booking(database_engine, psychologist.id)

    def confirm_with_same_reference(result):
        with Session(database_engine) as session:
            outcome = booking_api.confirm_held_booking(
                session,
                booking_id,
                booking_adapter.BookingPaymentResult(
                    payment_reference=result.provider_reference, succeeded=True
                ),
            )
        assert outcome == "CONFIRMED"

    gateway = RecordingGateway(
        FixedReferenceGateway("provider-known-ref"), before_return=confirm_with_same_reference
    )

    payment = pay(database_engine, booking_id, "key-same-ref-0001", gateway)

    assert payment.status is PaymentStatus.SUCCEEDED
    assert payment.booking_decision is BookingConfirmationDecision.ALREADY_CONFIRMED
    booking = booking_record(database_engine, booking_id)
    assert (booking.status, booking.payment_reference) == (
        BookingStatus.CONFIRMED,
        "provider-known-ref",
    )


def test_expired_booking_is_rejected_before_any_charge(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)
    expire_hold(database_engine, booking_id)
    gateway = succeeding()

    with pytest.raises(BookingNotPayable):
        pay(database_engine, booking_id, "key-late-0001", gateway)

    assert gateway.calls == []
    assert payment_rows(database_engine, booking_id) == []
    assert booking_record(database_engine, booking_id).status != BookingStatus.CONFIRMED


def test_unknown_booking_is_rejected_before_any_charge(database_engine):
    gateway = succeeding()

    with pytest.raises(BookingNotPayable):
        pay(database_engine, uuid4(), "key-unknown-0001", gateway)

    assert gateway.calls == []
    assert payment_rows(database_engine) == []


def test_free_booking_cannot_be_paid_through_the_gateway(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id, price_minor=0)
    gateway = succeeding()

    with pytest.raises(InvalidPaymentRequest):
        pay(database_engine, booking_id, "key-free-0001", gateway)

    assert gateway.calls == []
    assert payment_rows(database_engine, booking_id) == []


# Idempotency and double confirmation


def test_same_key_retry_returns_recorded_payment_without_charging_again(
    database_engine, psychologist
):
    booking_id = create_held_booking(database_engine, psychologist.id)
    gateway = succeeding()

    first = pay(database_engine, booking_id, "key-retry-0001", gateway)
    repeated = pay(database_engine, booking_id, "key-retry-0001", gateway)

    assert repeated.payment_id == first.payment_id
    assert repeated.status is PaymentStatus.SUCCEEDED
    assert repeated.provider_reference == first.provider_reference
    assert repeated.idempotent_replay is True
    assert len(gateway.calls) == 1
    assert len(payment_rows(database_engine, booking_id)) == 1


@pytest.mark.parametrize(
    "change", ["booking", "details"], ids=["different-booking", "different-result"]
)
def test_same_key_for_a_different_request_conflicts(database_engine, psychologist, change):
    booking_id = create_held_booking(database_engine, psychologist.id)
    other_booking_id = create_held_booking(database_engine, psychologist.id, offset_minutes=50)
    pay(database_engine, booking_id, "key-conflict-0001", failing(), "failure")
    gateway = succeeding()

    with pytest.raises(PaymentIdempotencyConflict):
        if change == "booking":
            pay(database_engine, other_booking_id, "key-conflict-0001", gateway, "failure")
        else:
            pay(database_engine, booking_id, "key-conflict-0001", gateway, "success")

    assert gateway.calls == []
    assert len(payment_rows(database_engine)) == 1


def test_confirmed_booking_cannot_be_paid_again_with_a_new_key(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)
    first = pay(database_engine, booking_id, "key-double-0001", succeeding())
    gateway = succeeding()

    with pytest.raises(BookingNotPayable):
        pay(database_engine, booking_id, "key-double-0002", gateway)

    assert gateway.calls == []
    assert [row.id for row in payment_rows(database_engine, booking_id)] == [first.payment_id]
    assert booking_record(database_engine, booking_id).payment_reference == (
        first.provider_reference
    )


# Failure recovery


def test_charge_interruption_leaves_pending_record_that_same_key_retry_resumes(
    database_engine, psychologist
):
    booking_id = create_held_booking(database_engine, psychologist.id)
    interrupted = RecordingGateway(
        MockPaymentGateway(PaymentOutcome.SUCCEEDED), error=RuntimeError("connection lost")
    )

    with pytest.raises(RuntimeError):
        pay(database_engine, booking_id, "key-crash-0001", interrupted)

    [pending] = payment_rows(database_engine, booking_id)
    assert pending.status == "pending"
    assert pending.provider_reference is None
    assert booking_record(database_engine, booking_id).status == BookingStatus.HELD

    other_gateway = succeeding()
    with pytest.raises(PaymentInProgress):
        pay(database_engine, booking_id, "key-crash-0002", other_gateway)
    assert other_gateway.calls == []

    resumed = pay(database_engine, booking_id, "key-crash-0001", succeeding())

    assert resumed.payment_id == pending.id
    assert resumed.status is PaymentStatus.SUCCEEDED
    assert resumed.idempotent_replay is True
    assert booking_record(database_engine, booking_id).status == BookingStatus.CONFIRMED


def test_booking_confirmation_error_keeps_successful_charge_for_manual_review(
    database_engine, psychologist, monkeypatch
):
    booking_id = create_held_booking(database_engine, psychologist.id)

    def broken_confirmation(session, booking_id, payment_reference):
        raise RuntimeError("booking unavailable")

    monkeypatch.setattr(booking_adapter, "confirm_booking", broken_confirmation)

    payment = pay(database_engine, booking_id, "key-broken-0001", succeeding())

    assert payment.status is PaymentStatus.MANUAL_REVIEW
    assert payment.booking_decision is None
    assert payment.provider_reference is not None
    [row] = payment_rows(database_engine, booking_id)
    assert (row.status, row.provider_reference) == ("manual_review", payment.provider_reference)
    assert booking_record(database_engine, booking_id).status == BookingStatus.HELD


def test_unconfirmed_successful_charge_blocks_new_attempts_with_other_keys(
    database_engine, psychologist, monkeypatch
):
    booking_id = create_held_booking(database_engine, psychologist.id)

    def broken_confirmation(session, booking_id, payment_reference):
        raise RuntimeError("booking unavailable")

    monkeypatch.setattr(booking_adapter, "confirm_booking", broken_confirmation)
    first_gateway = succeeding()
    first = pay(database_engine, booking_id, "key-review-block-0001", first_gateway)
    assert first.status is PaymentStatus.MANUAL_REVIEW
    assert booking_record(database_engine, booking_id).status == BookingStatus.HELD

    other_gateway = succeeding()
    with pytest.raises(PaymentRequiresManualReview):
        pay(database_engine, booking_id, "key-review-block-0002", other_gateway)
    assert other_gateway.calls == []

    replay_gateway = succeeding()
    replay = pay(database_engine, booking_id, "key-review-block-0001", replay_gateway)
    assert replay.payment_id == first.payment_id
    assert replay.status is PaymentStatus.MANUAL_REVIEW
    assert replay.idempotent_replay is True
    assert replay_gateway.calls == []

    assert len(first_gateway.calls) == 1
    rows = payment_rows(database_engine, booking_id)
    assert [(row.status, row.provider_reference) for row in rows] == [
        ("manual_review", first.provider_reference)
    ]
    assert booking_record(database_engine, booking_id).status == BookingStatus.HELD


def test_booking_confirmation_timeout_keeps_successful_charge_for_manual_review(
    database_engine, psychologist, monkeypatch
):
    booking_id = create_held_booking(database_engine, psychologist.id)
    real_confirmation = booking_adapter.confirm_booking

    def confirmation_with_short_lock_timeout(session, booking_id, payment_reference):
        # SET LOCAL runs inside the settlement savepoint and is undone when it rolls back.
        session.execute(text("SET LOCAL lock_timeout = '200ms'"))
        return real_confirmation(session, booking_id, payment_reference)

    monkeypatch.setattr(booking_adapter, "confirm_booking", confirmation_with_short_lock_timeout)
    gateway = succeeding()

    with Session(database_engine) as blocker, blocker.begin():
        # Another transaction holds the booking row, so booking's confirmation times out. FOR NO
        # KEY UPDATE still lets the payment insert take its foreign-key share lock.
        blocker.execute(
            select(Booking).where(Booking.id == booking_id).with_for_update(key_share=True)
        )
        payment = pay(database_engine, booking_id, "key-timeout-0001", gateway)

    assert len(gateway.calls) == 1
    assert payment.status is PaymentStatus.MANUAL_REVIEW
    assert payment.booking_decision is None
    assert payment.provider_reference is not None
    [row] = payment_rows(database_engine, booking_id)
    assert (row.status, row.provider_reference) == ("manual_review", payment.provider_reference)
    booking = booking_record(database_engine, booking_id)
    assert booking.status == BookingStatus.HELD
    assert booking.payment_reference is None

    other_gateway = succeeding()
    with pytest.raises(PaymentRequiresManualReview):
        pay(database_engine, booking_id, "key-timeout-0002", other_gateway)
    assert other_gateway.calls == []


def test_simulated_confirmation_timeout_is_a_real_postgresql_error(database_engine, psychologist):
    """Guard for the test above: the lock timeout it relies on raises OperationalError."""
    booking_id = create_held_booking(database_engine, psychologist.id)
    with Session(database_engine) as blocker, blocker.begin():
        blocker.execute(
            select(Booking).where(Booking.id == booking_id).with_for_update(key_share=True)
        )
        with Session(database_engine) as session, session.begin():
            session.execute(text("SET LOCAL lock_timeout = '200ms'"))
            with pytest.raises(OperationalError):
                session.execute(select(Booking).where(Booking.id == booking_id).with_for_update())


def test_pay_booking_refuses_a_caller_transaction(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)

    with Session(database_engine) as session, session.begin():
        with pytest.raises(RuntimeError):
            pay_booking(session, booking_id, "key-caller-tx-0001", succeeding())


# Concurrency


def test_concurrent_requests_with_the_same_key_charge_once(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)
    gateway = succeeding()
    barrier = Barrier(3)

    def attempt():
        barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        return pay(database_engine, booking_id, "key-concurrent-same", gateway)

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: attempt(), range(3)))

    assert len({result.payment_id for result in results}) == 1
    assert {result.status for result in results} == {PaymentStatus.SUCCEEDED}
    assert [result.idempotent_replay for result in results].count(False) == 1
    assert len(gateway.calls) == 1
    assert booking_record(database_engine, booking_id).status == BookingStatus.CONFIRMED


def test_concurrent_requests_with_different_keys_confirm_once(database_engine, psychologist):
    booking_id = create_held_booking(database_engine, psychologist.id)
    gateway = succeeding()
    barrier = Barrier(3)

    def attempt(index):
        barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        try:
            return pay(database_engine, booking_id, f"key-concurrent-diff-{index}", gateway)
        except (PaymentInProgress, BookingNotPayable) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(attempt, range(3)))

    succeeded = [result for result in results if getattr(result, "status", None) == "succeeded"]
    assert len(succeeded) == 1
    assert all(
        isinstance(result, (PaymentInProgress, BookingNotPayable))
        for result in results
        if result not in succeeded
    )
    assert len(gateway.calls) == 1
    rows = payment_rows(database_engine, booking_id)
    assert [row.status for row in rows] == ["succeeded"]
    assert booking_record(database_engine, booking_id).payment_reference == (
        succeeded[0].provider_reference
    )


def _waiting_advisory_locks(database_engine) -> int:
    with database_engine.connect() as connection:
        return connection.scalar(
            text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted")
        )


def test_attempt_arriving_during_failed_confirmation_is_blocked_without_charging(
    database_engine, psychologist, monkeypatch
):
    booking_id = create_held_booking(database_engine, psychologist.id)
    second_waiting = Event()

    def slow_broken_confirmation(session, booking_id, payment_reference):
        # Keep the booking's payment lock until the second attempt is queued behind it.
        deadline = datetime.now(UTC) + timedelta(seconds=BARRIER_TIMEOUT_SECONDS)
        while _waiting_advisory_locks(database_engine) == 0:
            assert datetime.now(UTC) < deadline, "second attempt never waited for the lock"
        second_waiting.set()
        raise RuntimeError("booking unavailable")

    monkeypatch.setattr(booking_adapter, "confirm_booking", slow_broken_confirmation)
    first_charged = Event()
    first_gateway = RecordingGateway(
        MockPaymentGateway(PaymentOutcome.SUCCEEDED),
        before_return=lambda result: first_charged.set(),
    )
    second_gateway = succeeding()

    def second_attempt():
        assert first_charged.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        try:
            return pay(database_engine, booking_id, "key-race-review-0002", second_gateway)
        except (PaymentRequiresManualReview, PaymentInProgress) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=1) as executor:
        second_future = executor.submit(second_attempt)
        first = pay(database_engine, booking_id, "key-race-review-0001", first_gateway)
        second = second_future.result(timeout=BARRIER_TIMEOUT_SECONDS)

    assert second_waiting.is_set()
    assert first.status is PaymentStatus.MANUAL_REVIEW
    assert isinstance(second, PaymentRequiresManualReview)
    assert len(first_gateway.calls) == 1
    assert second_gateway.calls == []
    assert [row.status for row in payment_rows(database_engine, booking_id)] == ["manual_review"]
    assert booking_record(database_engine, booking_id).status == BookingStatus.HELD


def test_concurrent_attempts_with_failing_confirmation_charge_once(
    database_engine, psychologist, monkeypatch
):
    booking_id = create_held_booking(database_engine, psychologist.id)

    def broken_confirmation(session, booking_id, payment_reference):
        raise RuntimeError("booking unavailable")

    monkeypatch.setattr(booking_adapter, "confirm_booking", broken_confirmation)
    gateway = succeeding()
    barrier = Barrier(4)

    def attempt(index):
        barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
        try:
            return pay(database_engine, booking_id, f"key-concurrent-review-{index}", gateway)
        except (PaymentRequiresManualReview, PaymentInProgress) as exc:
            return exc

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, range(4)))

    recorded = [result for result in results if not isinstance(result, Exception)]
    assert [result.status for result in recorded] == [PaymentStatus.MANUAL_REVIEW]
    assert len(gateway.calls) == 1
    assert [row.status for row in payment_rows(database_engine, booking_id)] == ["manual_review"]
    assert booking_record(database_engine, booking_id).status == BookingStatus.HELD
