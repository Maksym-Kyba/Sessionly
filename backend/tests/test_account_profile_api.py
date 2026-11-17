from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.auth_service import create_session
from app.accounts.service import update_psychologist_profile
from app.booking.models import Booking, BookingStatus
from app.availability.models import AvailabilitySlot
from app.availability.schemas import AvailabilityRuleInput
from app.availability.service import create_rule
from app.core.config import settings


async def _sign_in(api_client, database_engine, psychologist, monkeypatch) -> dict[str, str]:
    monkeypatch.setattr(settings, "csrf_secret_key", "profile-update-test-secret-value-32")
    monkeypatch.setattr(settings, "session_cookie_name", "sessionly_profile_test")
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    with Session(database_engine) as session:
        raw_token = create_session(session, psychologist.id, settings)
    api_client.cookies.set(settings.session_cookie_name, raw_token)
    response = await api_client.get("/api/v1/accounts/me")
    assert response.status_code == 200
    return {
        "Origin": "http://localhost:3000",
        "X-CSRF-Token": response.json()["csrf_token"],
    }


@pytest.mark.anyio
async def test_authenticated_psychologist_can_update_profile(
    api_client, database_engine, psychologist, monkeypatch
):
    headers = await _sign_in(api_client, database_engine, psychologist, monkeypatch)

    response = await api_client.patch(
        "/api/v1/accounts/me",
        json={"display_name": "  Dr. New Name  ", "time_zone": " America/New_York "},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["public_id"] == psychologist.public_id
    assert response.json()["display_name"] == "Dr. New Name"
    assert response.json()["time_zone"] == "America/New_York"
    assert response.json()["email"] == psychologist.email
    assert response.json()["csrf_token"] == headers["X-CSRF-Token"]
    with Session(database_engine) as session:
        updated = session.get(type(psychologist), psychologist.id)
        assert updated is not None
        assert updated.display_name == "Dr. New Name"
        assert updated.time_zone == "America/New_York"


@pytest.mark.anyio
async def test_profile_patch_updates_only_fields_that_were_provided(
    api_client, database_engine, psychologist, monkeypatch
):
    headers = await _sign_in(api_client, database_engine, psychologist, monkeypatch)

    response = await api_client.patch(
        "/api/v1/accounts/me", json={"display_name": "Updated Name"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Updated Name"
    assert response.json()["time_zone"] == "Europe/Kyiv"


@pytest.mark.anyio
async def test_empty_profile_patch_is_a_no_op(
    api_client, database_engine, psychologist, monkeypatch
):
    headers = await _sign_in(api_client, database_engine, psychologist, monkeypatch)

    response = await api_client.patch("/api/v1/accounts/me", json={}, headers=headers)

    assert response.status_code == 200
    assert response.json()["display_name"] == "Test Psychologist"
    assert response.json()["time_zone"] == "Europe/Kyiv"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"display_name": ""},
        {"display_name": "   "},
        {"display_name": "x" * 201},
        {"display_name": None},
        {"time_zone": "  "},
        {"time_zone": "Not/A_Real_Zone"},
        {"time_zone": None},
    ],
)
async def test_profile_patch_rejects_invalid_values(
    api_client, database_engine, psychologist, monkeypatch, payload
):
    headers = await _sign_in(api_client, database_engine, psychologist, monkeypatch)

    response = await api_client.patch("/api/v1/accounts/me", json=payload, headers=headers)

    assert response.status_code == 422
    with Session(database_engine) as session:
        unchanged = session.get(type(psychologist), psychologist.id)
        assert unchanged is not None
        assert unchanged.display_name == "Test Psychologist"
        assert unchanged.time_zone == "Europe/Kyiv"


@pytest.mark.anyio
async def test_profile_patch_requires_authentication(api_client):
    response = await api_client.patch(
        "/api/v1/accounts/me",
        json={"display_name": "Unauthorized Update"},
        headers={"Origin": "http://localhost:3000", "X-CSRF-Token": "invalid"},
    )

    assert response.status_code == 401


@pytest.mark.anyio
async def test_profile_patch_requires_a_valid_csrf_token(
    api_client, database_engine, psychologist, monkeypatch
):
    headers = await _sign_in(api_client, database_engine, psychologist, monkeypatch)

    response = await api_client.patch(
        "/api/v1/accounts/me",
        json={"display_name": "CSRF Rejected"},
        headers={**headers, "X-CSRF-Token": "invalid"},
    )

    assert response.status_code == 403
    with Session(database_engine) as session:
        unchanged = session.get(type(psychologist), psychologist.id)
        assert unchanged is not None
        assert unchanged.display_name == "Test Psychologist"


@pytest.mark.anyio
async def test_time_zone_update_reconciles_future_materialized_slots(
    api_client, database_engine, psychologist, monkeypatch
):
    headers = await _sign_in(api_client, database_engine, psychologist, monkeypatch)
    target_date = datetime.now(UTC).date() + timedelta(days=7)
    with Session(database_engine) as session:
        rule = create_rule(
            session,
            psychologist.id,
            AvailabilityRuleInput(
                weekday=target_date.weekday(),
                local_start=time(9),
                local_end=time(11),
                session_duration_minutes=60,
                price_minor=120000,
                currency="UAH",
                valid_from=target_date,
                valid_until=target_date,
            ),
        )
        original_rule_id = rule.id
    with Session(database_engine) as session:
        old_slots = session.scalars(
            select(AvailabilitySlot).where(
                AvailabilitySlot.psychologist_id == psychologist.id,
                AvailabilitySlot.availability_rule_id == original_rule_id,
                AvailabilitySlot.state == "published",
            )
        ).all()
        assert old_slots
        old_starts = {slot.starts_at for slot in old_slots}
        old_slots_by_start = {slot.starts_at: slot for slot in old_slots}

    now = datetime.now(UTC)
    held_slot, confirmed_slot = sorted(old_slots_by_start.values(), key=lambda slot: slot.starts_at)
    with Session(database_engine) as session, session.begin():
        session.add_all(
            [
                Booking(
                    availability_slot_id=held_slot.id,
                    psychologist_id=psychologist.id,
                    starts_at=held_slot.starts_at,
                    ends_at=held_slot.ends_at,
                    session_duration_minutes=60,
                    price_minor=held_slot.price_minor,
                    currency=held_slot.currency,
                    status=BookingStatus.HELD,
                ),
                Booking(
                    availability_slot_id=confirmed_slot.id,
                    psychologist_id=psychologist.id,
                    starts_at=confirmed_slot.starts_at,
                    ends_at=confirmed_slot.ends_at,
                    session_duration_minutes=60,
                    price_minor=confirmed_slot.price_minor,
                    currency=confirmed_slot.currency,
                    status=BookingStatus.CONFIRMED,
                    confirmed_at=now,
                    payment_reference="timezone-profile-test-payment",
                ),
            ]
        )
    with Session(database_engine) as session:
        booking_snapshots = {
            booking.status: (
                booking.starts_at,
                booking.ends_at,
                booking.session_duration_minutes,
                booking.price_minor,
                booking.currency,
                booking.payment_reference,
                booking.hold_expires_at,
                booking.confirmed_at,
            )
            for booking in session.scalars(
                select(Booking).where(Booking.psychologist_id == psychologist.id)
            )
        }

    def fail_slot_refresh(*args, **kwargs):
        raise RuntimeError("simulated availability reconciliation failure")

    with monkeypatch.context() as patcher:
        patcher.setattr("app.availability.api.refresh_slots", fail_slot_refresh)
        with Session(database_engine) as session, pytest.raises(RuntimeError):
            update_psychologist_profile(session, psychologist.id, {"time_zone": "America/New_York"})
    with Session(database_engine) as session:
        unchanged = session.get(type(psychologist), psychologist.id)
        assert unchanged is not None and unchanged.time_zone == "Europe/Kyiv"
        assert (
            session.scalar(
                select(AvailabilitySlot.id).where(
                    AvailabilitySlot.id == held_slot.id,
                    AvailabilitySlot.state == "published",
                )
            )
            is not None
        )
    response = await api_client.patch(
        "/api/v1/accounts/me", json={"time_zone": "America/New_York"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["time_zone"] == "America/New_York"
    with Session(database_engine) as session:
        slots = session.scalars(
            select(AvailabilitySlot).where(
                AvailabilitySlot.psychologist_id == psychologist.id,
                AvailabilitySlot.availability_rule_id == original_rule_id,
            )
        ).all()
        assert any(slot.state == "withdrawn" for slot in slots)
        new_starts = {slot.starts_at for slot in slots if slot.state == "published"}
        assert new_starts
        assert new_starts.isdisjoint(old_starts)
        updated_bookings = {
            booking.status: (
                booking.starts_at,
                booking.ends_at,
                booking.session_duration_minutes,
                booking.price_minor,
                booking.currency,
                booking.payment_reference,
                booking.hold_expires_at,
                booking.confirmed_at,
            )
            for booking in session.scalars(
                select(Booking).where(Booking.psychologist_id == psychologist.id)
            )
        }
        assert updated_bookings == booking_snapshots
