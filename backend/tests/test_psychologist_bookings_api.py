from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.models import Psychologist
from app.availability.models import AvailabilitySlot
from app.booking.models import Booking, BookingStatus


def add_booking(
    session: Session,
    psychologist_id: UUID,
    *,
    booking_id: UUID,
    starts_at: datetime,
    status: BookingStatus,
    client_email: str | None = "client@example.test",
    hold_expires_at: datetime | None = None,
) -> UUID:
    slot = session.scalar(
        select(AvailabilitySlot).where(
            AvailabilitySlot.psychologist_id == psychologist_id,
            AvailabilitySlot.starts_at == starts_at,
            AvailabilitySlot.ends_at == starts_at + timedelta(minutes=50),
        )
    )
    if slot is None:
        slot = AvailabilitySlot(
            psychologist_id=psychologist_id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=50),
            price_minor=120000,
            currency="UAH",
            state="published",
        )
        session.add(slot)
        session.flush()
    session.add(
        Booking(
            id=booking_id,
            availability_slot_id=slot.id,
            psychologist_id=psychologist_id,
            starts_at=slot.starts_at,
            ends_at=slot.ends_at,
            session_duration_minutes=50,
            price_minor=slot.price_minor,
            currency=slot.currency,
            client_email=client_email,
            status=status,
            hold_expires_at=hold_expires_at or datetime.now(UTC) + timedelta(minutes=15),
        )
    )
    return slot.id


@pytest.mark.anyio
async def test_psychologist_bookings_requires_authentication(api_client):
    response = await api_client.get("/api/v1/accounts/me/bookings")

    assert response.status_code == 401


@pytest.mark.anyio
async def test_psychologist_bookings_are_scoped_and_include_snapshots(
    authenticated_client, database_engine, psychologist
):
    now = datetime.now(UTC) + timedelta(days=5)
    own_booking_id = uuid4()
    stale_hold_id = uuid4()
    foreign_booking_id = uuid4()
    with Session(database_engine) as session, session.begin():
        other_psychologist = Psychologist(
            display_name="Other Psychologist",
            email="other@example.test",
            time_zone="Europe/Kyiv",
        )
        session.add(other_psychologist)
        session.flush()
        add_booking(
            session,
            psychologist.id,
            booking_id=own_booking_id,
            starts_at=now,
            status=BookingStatus.CONFIRMED,
        )
        add_booking(
            session,
            psychologist.id,
            booking_id=stale_hold_id,
            starts_at=now + timedelta(days=1),
            status=BookingStatus.HELD,
            hold_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        add_booking(
            session,
            other_psychologist.id,
            booking_id=foreign_booking_id,
            starts_at=now + timedelta(days=1),
            status=BookingStatus.CONFIRMED,
            client_email="private@example.test",
        )

    response = await authenticated_client.get("/api/v1/accounts/me/bookings")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    assert payload["total"] == 2
    assert payload["limit"] == 20
    assert payload["offset"] == 0
    bookings_by_id = {item["id"]: item for item in payload["items"]}
    assert set(bookings_by_id) == {str(own_booking_id), str(stale_hold_id)}
    assert bookings_by_id[str(own_booking_id)]["status"] == "CONFIRMED"
    assert bookings_by_id[str(own_booking_id)]["client_email"] == "client@example.test"
    assert datetime.fromisoformat(bookings_by_id[str(own_booking_id)]["starts_at"]) == now
    assert datetime.fromisoformat(
        bookings_by_id[str(own_booking_id)]["ends_at"]
    ) == now + timedelta(minutes=50)
    assert bookings_by_id[str(own_booking_id)]["session_duration_minutes"] == 50
    assert bookings_by_id[str(own_booking_id)]["price_minor"] == 120000
    assert bookings_by_id[str(own_booking_id)]["currency"] == "UAH"
    assert bookings_by_id[str(stale_hold_id)]["status"] == "EXPIRED"
    with Session(database_engine) as session:
        persisted_stale_hold = session.get(Booking, stale_hold_id)
        persisted_booking = session.get(Booking, own_booking_id)
        assert persisted_stale_hold is not None
        assert persisted_booking is not None
        assert persisted_stale_hold.status == BookingStatus.HELD
        assert (
            datetime.fromisoformat(bookings_by_id[str(own_booking_id)]["created_at"])
            == persisted_booking.created_at
        )
    assert str(foreign_booking_id) not in response.text
    assert "private@example.test" not in response.text


@pytest.mark.anyio
async def test_psychologist_bookings_order_and_paginate_deterministically(
    authenticated_client, database_engine, psychologist
):
    now = datetime.now(UTC) + timedelta(days=5)
    first_id = UUID(int=10)
    tied_first_id = UUID(int=20)
    tied_second_id = UUID(int=30)
    last_id = UUID(int=40)
    with Session(database_engine) as session, session.begin():
        add_booking(
            session,
            psychologist.id,
            booking_id=last_id,
            starts_at=now + timedelta(days=2),
            status=BookingStatus.EXPIRED,
        )
        add_booking(
            session,
            psychologist.id,
            booking_id=tied_second_id,
            starts_at=now + timedelta(days=1),
            status=BookingStatus.EXPIRED,
        )
        add_booking(
            session,
            psychologist.id,
            booking_id=first_id,
            starts_at=now,
            status=BookingStatus.HELD,
        )
        add_booking(
            session,
            psychologist.id,
            booking_id=tied_first_id,
            starts_at=now + timedelta(days=1),
            status=BookingStatus.EXPIRED,
        )

    first_page = await authenticated_client.get("/api/v1/accounts/me/bookings", params={"limit": 2})
    second_page = await authenticated_client.get(
        "/api/v1/accounts/me/bookings", params={"limit": 2, "offset": 2}
    )

    assert first_page.status_code == second_page.status_code == 200
    assert [item["id"] for item in first_page.json()["items"]] == [
        str(first_id),
        str(tied_first_id),
    ]
    assert [item["id"] for item in second_page.json()["items"]] == [
        str(tied_second_id),
        str(last_id),
    ]
    assert [item["status"] for item in first_page.json()["items"]] == ["HELD", "EXPIRED"]
    assert [item["status"] for item in second_page.json()["items"]] == [
        "EXPIRED",
        "EXPIRED",
    ]
    assert first_page.json()["total"] == second_page.json()["total"] == 4
    assert first_page.json()["limit"] == second_page.json()["limit"] == 2
    assert second_page.json()["offset"] == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 100_001}]
)
async def test_psychologist_bookings_returns_empty_page_and_validates_pagination(
    authenticated_client, params
):
    response = await authenticated_client.get("/api/v1/accounts/me/bookings")
    invalid_page = await authenticated_client.get("/api/v1/accounts/me/bookings", params=params)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}
    assert invalid_page.status_code == 422
