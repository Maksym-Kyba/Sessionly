from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, time, timedelta
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.availability import service as availability_service
from app.availability.models import AvailabilitySlot
from app.availability.schemas import AvailabilityRuleInput
from app.booking import api as booking_api
from app.booking.models import Booking, BookingStatus
from app.booking.api import BookingConflict
from app.booking.schemas import ConfirmationOutcome, PaymentResult


def add_slot(
    session: Session,
    psychologist_id,
    starts_at: datetime,
    ends_at: datetime,
    *,
    price_minor: int = 120000,
    currency: str = "UAH",
) -> AvailabilitySlot:
    slot = AvailabilitySlot(
        psychologist_id=psychologist_id,
        starts_at=starts_at,
        ends_at=ends_at,
        price_minor=price_minor,
        currency=currency,
        state="published",
    )
    session.add(slot)
    session.flush()
    return slot


def expire_for_test(session: Session, booking_id) -> None:
    booking = session.get(Booking, booking_id)
    assert booking is not None
    booking.hold_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.flush()
    session.refresh(booking)


def create_future_slot(database_engine, psychologist_id, *, start_offset_minutes=0):
    starts_at = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(days=2)
    starts_at += timedelta(minutes=start_offset_minutes)
    with Session(database_engine) as session, session.begin():
        slot = add_slot(session, psychologist_id, starts_at, starts_at + timedelta(minutes=50))
        return slot.id, starts_at, starts_at + timedelta(minutes=50)


def test_create_hold_stores_exact_expiry_and_immutable_snapshots(database_engine, psychologist):
    slot_id, starts_at, ends_at = create_future_slot(database_engine, psychologist.id)
    with Session(database_engine) as session:
        booking = booking_api.create_hold(session, slot_id)
        assert booking.status == BookingStatus.HELD
        assert booking.created_at.tzinfo is not None
        assert booking.hold_expires_at - booking.created_at == timedelta(minutes=15)
        assert booking.starts_at == starts_at
        assert booking.ends_at == ends_at
        assert booking.session_duration_minutes == 50
        assert booking.price_minor == 120000
        assert booking.currency == "UAH"

        slot = session.get(AvailabilitySlot, slot_id)
        assert slot is not None
        slot.price_minor = 175000
        slot.starts_at += timedelta(hours=1)
        slot.ends_at += timedelta(hours=1)
        session.commit()
        persisted_booking = session.get(Booking, booking.id)
        assert persisted_booking is not None
        assert persisted_booking.starts_at == starts_at
        assert persisted_booking.ends_at == ends_at
        assert persisted_booking.price_minor == 120000


def test_past_availability_slot_cannot_be_held(database_engine, psychologist):
    starts_at = datetime.now(UTC) - timedelta(hours=2)
    with Session(database_engine) as session, session.begin():
        slot = add_slot(session, psychologist.id, starts_at, starts_at + timedelta(minutes=50))
        slot_id = slot.id

    with Session(database_engine) as session:
        with pytest.raises(BookingConflict):
            booking_api.create_hold(session, slot_id)


def test_expired_hold_is_released_and_replaced_atomically(database_engine, psychologist):
    slot_id, _, _ = create_future_slot(database_engine, psychologist.id)
    with Session(database_engine) as session:
        original = booking_api.create_hold(session, slot_id)
        original_id = original.id
        expire_for_test(session, original.id)
        session.commit()

        replacement = booking_api.create_hold(session, slot_id)
        assert replacement.id != original_id
        assert replacement.status == BookingStatus.HELD
        previous = session.get(Booking, original_id)
        assert previous is not None
        assert previous.status == BookingStatus.EXPIRED


def test_concurrent_replacements_of_expired_hold_have_one_winner(database_engine, psychologist):
    slot_id, _, _ = create_future_slot(database_engine, psychologist.id)
    with Session(database_engine) as session:
        old_booking = booking_api.create_hold(session, slot_id)
        old_booking_id = old_booking.id
        expire_for_test(session, old_booking_id)
        session.commit()

    start_barrier = Barrier(2)

    def replace_hold():
        with Session(database_engine) as session:
            start_barrier.wait(timeout=5)
            try:
                return booking_api.create_hold(session, slot_id).id
            except BookingConflict:
                return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: replace_hold(), range(2)))
    assert sum(outcome is not None for outcome in outcomes) == 1
    with Session(database_engine) as session:
        old_booking = session.get(Booking, old_booking_id)
        active = session.scalars(select(Booking).where(Booking.status == BookingStatus.HELD)).all()
        assert old_booking is not None and old_booking.status == BookingStatus.EXPIRED
        assert len(active) == 1


def test_adjacent_appointments_are_allowed(database_engine, psychologist):
    first_id, starts_at, ends_at = create_future_slot(database_engine, psychologist.id)
    second_id, _, _ = create_future_slot(database_engine, psychologist.id, start_offset_minutes=50)
    with Session(database_engine) as session:
        first = booking_api.create_hold(session, first_id)
        second = booking_api.create_hold(session, second_id)
        assert first.ends_at == second.starts_at


def test_database_exclusion_constraint_rejects_overlapping_intervals(database_engine, psychologist):
    starts_at = datetime.now(UTC) + timedelta(days=3)
    with Session(database_engine) as session:
        first_slot = add_slot(
            session, psychologist.id, starts_at, starts_at + timedelta(minutes=60)
        )
        second_slot = add_slot(
            session,
            psychologist.id,
            starts_at + timedelta(minutes=30),
            starts_at + timedelta(minutes=90),
        )
        first = Booking(
            availability_slot_id=first_slot.id,
            psychologist_id=psychologist.id,
            starts_at=first_slot.starts_at,
            ends_at=first_slot.ends_at,
            session_duration_minutes=60,
            price_minor=first_slot.price_minor,
            currency=first_slot.currency,
            status=BookingStatus.HELD,
        )
        second = Booking(
            availability_slot_id=second_slot.id,
            psychologist_id=psychologist.id,
            starts_at=second_slot.starts_at,
            ends_at=second_slot.ends_at,
            session_duration_minutes=60,
            price_minor=second_slot.price_minor,
            currency=second_slot.currency,
            status=BookingStatus.HELD,
        )
        session.add(first)
        session.flush()
        session.add(second)
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()


@pytest.mark.parametrize("overlap_minutes", [0, 25])
def test_concurrent_booking_requests_cannot_claim_overlapping_slots(
    database_engine, psychologist, overlap_minutes
):
    first_id, starts_at, ends_at = create_future_slot(database_engine, psychologist.id)
    if overlap_minutes:
        second_starts = starts_at + timedelta(minutes=overlap_minutes)
        with Session(database_engine) as session, session.begin():
            second = add_slot(
                session, psychologist.id, second_starts, second_starts + timedelta(minutes=50)
            )
            second_id = second.id
    else:
        second_id = first_id

    start_barrier = Barrier(2)

    def request_hold(slot_id):
        with Session(database_engine) as session:
            start_barrier.wait(timeout=5)
            try:
                return booking_api.create_hold(session, slot_id).id
            except BookingConflict:
                return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(request_hold, [first_id, second_id]))
    assert sum(outcome is not None for outcome in outcomes) == 1
    with Session(database_engine) as session:
        active = session.scalars(select(Booking).where(Booking.status == BookingStatus.HELD)).all()
        assert len(active) == 1


def test_public_slot_filter_ignores_expired_holds(database_engine, psychologist):
    slot_id, starts_at, ends_at = create_future_slot(database_engine, psychologist.id)
    with Session(database_engine) as session:
        booking = booking_api.create_hold(session, slot_id)
        interval = [(slot_id, starts_at, ends_at)]
        assert booking_api.available_slot_ids(session, psychologist.id, interval) == set()
        expire_for_test(session, booking.id)
        session.flush()
        assert booking_api.available_slot_ids(session, psychologist.id, interval) == {slot_id}


def test_payment_integration_api_uses_booking_snapshot_and_idempotent_reference(
    database_engine, psychologist
):
    slot_id, _, _ = create_future_slot(database_engine, psychologist.id)
    with Session(database_engine) as session:
        booking = booking_api.create_hold(session, slot_id)
        payable = booking_api.get_payable_booking(session, booking.id)
        assert payable is not None
        assert payable.amount_minor == booking.price_minor
        assert payable.currency == booking.currency
        assert (
            booking_api.confirm_held_booking(
                session,
                booking.id,
                PaymentResult(payment_reference="failed-payment", succeeded=False),
            )
            == ConfirmationOutcome.NOT_CONFIRMABLE
        )

        payment = PaymentResult(payment_reference="mock-payment-1", succeeded=True)
        assert (
            booking_api.confirm_held_booking(session, booking.id, payment)
            == ConfirmationOutcome.CONFIRMED
        )
        assert (
            booking_api.confirm_held_booking(session, booking.id, payment)
            == ConfirmationOutcome.ALREADY_CONFIRMED
        )
        assert (
            booking_api.confirm_held_booking(
                session,
                booking.id,
                PaymentResult(payment_reference="different-payment", succeeded=True),
            )
            == ConfirmationOutcome.NOT_CONFIRMABLE
        )
        assert (
            booking_api.confirm_held_booking(
                session,
                booking.id,
                PaymentResult(payment_reference="x" * 256, succeeded=True),
            )
            == ConfirmationOutcome.NOT_CONFIRMABLE
        )


def test_duplicate_payment_reference_cannot_confirm_a_different_booking(
    database_engine, psychologist
):
    first_id, _, _ = create_future_slot(database_engine, psychologist.id)
    second_id, _, _ = create_future_slot(database_engine, psychologist.id, start_offset_minutes=50)
    with Session(database_engine) as session:
        first = booking_api.create_hold(session, first_id)
        second = booking_api.create_hold(session, second_id)
        payment = PaymentResult(payment_reference="one-provider-payment", succeeded=True)
        assert (
            booking_api.confirm_held_booking(session, first.id, payment)
            == ConfirmationOutcome.CONFIRMED
        )
        assert (
            booking_api.confirm_held_booking(session, second.id, payment)
            == ConfirmationOutcome.NOT_CONFIRMABLE
        )
        second_record = session.get(Booking, second.id)
        assert second_record is not None
        assert second_record.status == BookingStatus.HELD
        assert second_record.payment_reference is None


def test_expired_booking_cannot_be_confirmed_by_late_payment(database_engine, psychologist):
    slot_id, _, _ = create_future_slot(database_engine, psychologist.id)
    with Session(database_engine) as session:
        booking = booking_api.create_hold(session, slot_id)
        expire_for_test(session, booking.id)
        session.commit()
        assert booking_api.get_payable_booking(session, booking.id) is None
        outcome = booking_api.confirm_held_booking(
            session,
            booking.id,
            PaymentResult(payment_reference="late-payment", succeeded=True),
        )
        assert outcome == ConfirmationOutcome.EXPIRED
        refreshed = session.get(Booking, booking.id)
        assert refreshed is not None
        assert refreshed.status == BookingStatus.EXPIRED
        assert refreshed.payment_reference is None


def test_expired_hold_racing_with_late_confirmation_never_confirms(database_engine, psychologist):
    slot_id, _, _ = create_future_slot(database_engine, psychologist.id)
    with Session(database_engine) as session:
        old_booking = booking_api.create_hold(session, slot_id)
        old_booking_id = old_booking.id
        expire_for_test(session, old_booking_id)
        session.commit()

    start_barrier = Barrier(2)

    def replace_hold():
        with Session(database_engine) as session:
            start_barrier.wait(timeout=5)
            try:
                return booking_api.create_hold(session, slot_id).id
            except BookingConflict:
                return None

    def confirm_late_payment():
        with Session(database_engine) as session:
            start_barrier.wait(timeout=5)
            return booking_api.confirm_held_booking(
                session,
                old_booking_id,
                PaymentResult(payment_reference="late-race-payment", succeeded=True),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        replacement_future = executor.submit(replace_hold)
        confirmation_future = executor.submit(confirm_late_payment)
        replacement_id = replacement_future.result(timeout=10)
        confirmation = confirmation_future.result(timeout=10)

    assert replacement_id is not None
    assert confirmation == ConfirmationOutcome.EXPIRED
    with Session(database_engine) as session:
        old_booking = session.get(Booking, old_booking_id)
        replacement = session.get(Booking, replacement_id)
        assert old_booking is not None and old_booking.status == BookingStatus.EXPIRED
        assert old_booking.payment_reference is None
        assert replacement is not None and replacement.status == BookingStatus.HELD


@pytest.mark.parametrize("confirmed", [False, True])
@pytest.mark.parametrize("retire_rule", [False, True])
def test_availability_rule_update_preserves_active_booking(
    database_engine, psychologist, confirmed, retire_rule
):
    local_day = datetime.now(ZoneInfo(psychologist.time_zone)).date() + timedelta(days=3)
    rule_data = AvailabilityRuleInput(
        weekday=local_day.weekday(),
        local_start=time(10),
        local_end=time(11),
        session_duration_minutes=60,
        price_minor=120000,
        currency="UAH",
        valid_from=local_day,
        valid_until=local_day,
    )
    with Session(database_engine) as session:
        rule = availability_service.create_rule(session, psychologist.id, rule_data)
        rule_id = rule.id
        slot = session.scalar(
            select(AvailabilitySlot).where(
                AvailabilitySlot.psychologist_id == psychologist.id,
                AvailabilitySlot.availability_rule_id == rule.id,
            )
        )
        assert slot is not None
        booking = booking_api.create_hold(session, slot.id)
        session.commit()
        booking_id = booking.id
        session.commit()
        if confirmed:
            outcome = booking_api.confirm_held_booking(
                session,
                booking.id,
                PaymentResult(payment_reference="confirmed-payment", succeeded=True),
            )
            assert outcome == ConfirmationOutcome.CONFIRMED
            session.commit()

        if retire_rule:
            assert availability_service.retire_rule(session, psychologist.id, rule_id)
        else:
            updated = rule_data.model_copy(update={"price_minor": 155000})
            availability_service.update_rule(session, psychologist.id, rule_id, updated)

        preserved_booking = session.get(Booking, booking_id)
        preserved_slot = session.get(AvailabilitySlot, slot.id)
        assert preserved_booking is not None
        assert preserved_booking.status == (
            BookingStatus.CONFIRMED if confirmed else BookingStatus.HELD
        )
        assert preserved_booking.starts_at == slot.starts_at
        assert preserved_booking.ends_at == slot.ends_at
        assert preserved_booking.price_minor == 120000
        assert preserved_slot is not None
        if retire_rule:
            assert preserved_slot.state == "withdrawn"
            assert preserved_slot.price_minor == 120000
        else:
            assert preserved_slot.state == "published"
            assert preserved_slot.price_minor == 155000


def test_concurrent_hold_and_availability_update_complete_without_deadlock(
    database_engine, psychologist
):
    local_day = datetime.now(ZoneInfo(psychologist.time_zone)).date() + timedelta(days=3)
    rule_data = AvailabilityRuleInput(
        weekday=local_day.weekday(),
        local_start=time(10),
        local_end=time(11),
        session_duration_minutes=60,
        price_minor=120000,
        currency="UAH",
        valid_from=local_day,
        valid_until=local_day,
    )
    with Session(database_engine) as session:
        rule = availability_service.create_rule(session, psychologist.id, rule_data)
        rule_id = rule.id
        slot = session.scalar(
            select(AvailabilitySlot).where(
                AvailabilitySlot.psychologist_id == psychologist.id,
                AvailabilitySlot.availability_rule_id == rule_id,
            )
        )
        assert slot is not None
        slot_id = slot.id

    barrier = Barrier(2)

    def create_hold():
        with Session(database_engine) as session:
            barrier.wait(timeout=5)
            return booking_api.create_hold(session, slot_id).id

    def update_rule():
        with Session(database_engine) as session:
            barrier.wait(timeout=5)
            updated = rule_data.model_copy(update={"price_minor": 155000})
            assert availability_service.update_rule(session, psychologist.id, rule_id, updated)
            return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        hold_future = executor.submit(create_hold)
        update_future = executor.submit(update_rule)
        booking_id = hold_future.result(timeout=10)
        assert update_future.result(timeout=10)

    with Session(database_engine) as session:
        booking = session.get(Booking, booking_id)
        assert booking is not None and booking.status == BookingStatus.HELD
        assert booking.price_minor in {120000, 155000}


@pytest.mark.anyio
async def test_public_availability_hides_an_active_hold(api_client, database_engine, psychologist):
    local_day = datetime.now(ZoneInfo(psychologist.time_zone)).date() + timedelta(days=3)
    rule_data = AvailabilityRuleInput(
        weekday=local_day.weekday(),
        local_start=time(10),
        local_end=time(11),
        session_duration_minutes=60,
        price_minor=120000,
        currency="UAH",
        valid_from=local_day,
        valid_until=local_day,
    )
    with Session(database_engine) as session:
        rule = availability_service.create_rule(session, psychologist.id, rule_data)
        rule_id = rule.id
        slot = session.scalar(
            select(AvailabilitySlot).where(
                AvailabilitySlot.psychologist_id == psychologist.id,
                AvailabilitySlot.availability_rule_id == rule_id,
            )
        )
        assert slot is not None
        slot_id = slot.id
        session.commit()
        booking_api.create_hold(session, slot_id)

    timezone = ZoneInfo(psychologist.time_zone)
    window_start = datetime.combine(local_day, time.min, tzinfo=timezone).astimezone(UTC)
    window_end = window_start + timedelta(days=1)
    response = await api_client.get(
        f"/api/v1/psychologists/{psychologist.public_id}/availability",
        params={"from": window_start.isoformat(), "to": window_end.isoformat()},
    )
    assert response.status_code == 200
    assert response.json()["slots"] == []
