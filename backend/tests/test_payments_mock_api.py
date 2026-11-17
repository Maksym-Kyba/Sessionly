"""HTTP tests for the development-only mock payment endpoint.

Bookings and client access tokens are created through the real booking flow: email verification,
then `POST /api/v1/bookings`.
"""

import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.availability.models import AvailabilitySlot
from app.booking.models import Booking, BookingStatus
from app.core.config import settings
from app.main import app
from app.payments.models import Payment


def _key() -> str:
    return secrets.token_urlsafe(24)


def _add_future_slot(database_engine, psychologist_id, *, offset_minutes=0, price_minor=120000):
    starts_at = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(
        days=3, minutes=offset_minutes
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
        return slot.id


async def create_client_booking(
    client, sender, database_engine, psychologist, *, offset_minutes=0, price_minor=120000
) -> tuple[str, str]:
    """Return (booking_id, client_access_token) created through the public booking flow."""
    slot_id = _add_future_slot(
        database_engine, psychologist.id, offset_minutes=offset_minutes, price_minor=price_minor
    )
    email = f"client-{uuid4().hex[:12]}@example.test"
    requested = await client.post(
        "/api/v1/email-verifications",
        json={"email": email, "psychologist_public_id": psychologist.public_id},
    )
    assert requested.status_code == 202
    raw_token = re.search(r"#token=([^&]+)$", sender.messages[-1].verification_url)
    assert raw_token is not None
    consumed = await client.post(
        "/api/v1/email-verifications/consume",
        json={"token": raw_token.group(1), "psychologist_public_id": psychologist.public_id},
    )
    assert consumed.status_code == 200
    created = await client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": _key()},
        json={
            "slot_id": str(slot_id),
            "booking_verification_token": consumed.json()["booking_verification_token"],
        },
    )
    assert created.status_code == 201
    return created.json()["id"], created.json()["client_access_token"]


def headers_for(token: str, key: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {token}"}
    if key is not None:
        headers["Idempotency-Key"] = key
    return headers


def booking_status(database_engine, booking_id) -> str:
    with Session(database_engine) as session:
        return session.get(Booking, booking_id).status


def payment_count(database_engine) -> int:
    with Session(database_engine) as session:
        return session.scalar(select(func.count()).select_from(Payment))


def mock_path(booking_id) -> str:
    return f"/api/v1/bookings/{booking_id}/payments/mock"


@pytest.fixture
async def paid_booking_setup(api_client, email_sender, database_engine, psychologist):
    booking_id, token = await create_client_booking(
        api_client, email_sender, database_engine, psychologist
    )
    return booking_id, token


# Successful and failed payments


@pytest.mark.anyio
async def test_successful_mock_payment_returns_structured_response(
    api_client, database_engine, paid_booking_setup
):
    booking_id, token = paid_booking_setup

    response = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers_for(token, _key())
    )

    assert response.status_code == 201
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert body["booking_id"] == booking_id
    assert body["payment_status"] == "succeeded"
    assert body["booking_decision"] == "CONFIRMED"
    assert (body["amount_minor"], body["currency"]) == (120000, "UAH")
    assert body["provider"] == "mock"
    assert body["provider_reference"].startswith("mock_")
    assert body["idempotent_replay"] is False
    assert set(body) == {
        "payment_id",
        "booking_id",
        "payment_status",
        "booking_decision",
        "amount_minor",
        "currency",
        "provider",
        "provider_reference",
        "created_at",
        "updated_at",
        "idempotent_replay",
    }
    assert booking_status(database_engine, booking_id) == BookingStatus.CONFIRMED
    booking_read = await api_client.get(
        f"/api/v1/bookings/{booking_id}", headers=headers_for(token)
    )
    assert booking_read.json()["status"] == BookingStatus.CONFIRMED


@pytest.mark.anyio
async def test_repeated_request_is_replayed_with_200(
    api_client, database_engine, paid_booking_setup
):
    booking_id, token = paid_booking_setup
    headers = headers_for(token, _key())
    first = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers
    )

    repeated = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers
    )

    assert repeated.status_code == 200
    assert repeated.json()["payment_id"] == first.json()["payment_id"]
    assert repeated.json()["provider_reference"] == first.json()["provider_reference"]
    assert repeated.json()["idempotent_replay"] is True
    assert payment_count(database_engine) == 1


@pytest.mark.anyio
async def test_failed_mock_payment_leaves_booking_held(
    api_client, database_engine, paid_booking_setup
):
    booking_id, token = paid_booking_setup

    response = await api_client.post(
        mock_path(booking_id), json={"result": "failure"}, headers=headers_for(token, _key())
    )

    assert response.status_code == 201
    assert response.json()["payment_status"] == "failed"
    assert response.json()["booking_decision"] is None
    assert booking_status(database_engine, booking_id) == BookingStatus.HELD


@pytest.mark.anyio
async def test_second_payment_with_new_key_cannot_confirm_again(
    api_client, database_engine, paid_booking_setup
):
    booking_id, token = paid_booking_setup
    first = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers_for(token, _key())
    )

    second = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers_for(token, _key())
    )

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "Booking is not available for payment"
    assert payment_count(database_engine) == 1


# Client authorization


@pytest.mark.anyio
@pytest.mark.parametrize(
    "authorization",
    [None, "Token abc", "Bearer", "Bearer "],
    ids=["missing", "wrong-scheme", "no-token", "empty-token"],
)
async def test_missing_or_malformed_authorization_is_rejected(
    api_client, database_engine, paid_booking_setup, authorization
):
    booking_id, _ = paid_booking_setup
    headers = {"Idempotency-Key": _key()}
    if authorization is not None:
        headers["Authorization"] = authorization

    response = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Booking access is required"
    assert payment_count(database_engine) == 0
    assert booking_status(database_engine, booking_id) == BookingStatus.HELD


@pytest.mark.anyio
async def test_wrong_token_or_unknown_booking_is_not_found(
    api_client, database_engine, paid_booking_setup
):
    booking_id, token = paid_booking_setup

    wrong_token = await api_client.post(
        mock_path(booking_id),
        json={"result": "success"},
        headers=headers_for(secrets.token_urlsafe(32), _key()),
    )
    unknown_booking = await api_client.post(
        mock_path(uuid4()), json={"result": "success"}, headers=headers_for(token, _key())
    )

    assert wrong_token.status_code == 404
    assert unknown_booking.status_code == 404
    assert wrong_token.json()["detail"] == "Booking not found"
    assert payment_count(database_engine) == 0
    assert booking_status(database_engine, booking_id) == BookingStatus.HELD


@pytest.mark.anyio
async def test_token_for_one_booking_cannot_pay_another(
    api_client, email_sender, database_engine, psychologist
):
    first_id, first_token = await create_client_booking(
        api_client, email_sender, database_engine, psychologist
    )
    second_id, _ = await create_client_booking(
        api_client, email_sender, database_engine, psychologist, offset_minutes=50
    )

    response = await api_client.post(
        mock_path(second_id), json={"result": "success"}, headers=headers_for(first_token, _key())
    )

    assert response.status_code == 404
    assert payment_count(database_engine) == 0
    assert booking_status(database_engine, second_id) == BookingStatus.HELD
    assert booking_status(database_engine, first_id) == BookingStatus.HELD


@pytest.mark.anyio
async def test_expired_client_token_is_rejected(api_client, database_engine, paid_booking_setup):
    booking_id, token = paid_booking_setup
    with Session(database_engine) as session, session.begin():
        session.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(client_access_token_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )

    response = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers_for(token, _key())
    )

    assert response.status_code == 404
    assert payment_count(database_engine) == 0


@pytest.mark.anyio
async def test_replay_also_requires_the_client_token(
    api_client, database_engine, paid_booking_setup
):
    booking_id, token = paid_booking_setup
    key = _key()
    await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers_for(token, key)
    )

    replay_without_access = await api_client.post(
        mock_path(booking_id),
        json={"result": "success"},
        headers=headers_for(secrets.token_urlsafe(32), key),
    )

    assert replay_without_access.status_code == 404
    assert "payment_id" not in replay_without_access.json()


# Input validation and no client-controlled price


@pytest.mark.anyio
@pytest.mark.parametrize(
    "body",
    [
        {"result": "success", "amount_minor": 1},
        {"result": "success", "currency": "USD"},
        {"result": "success", "price_minor": 1},
        {"result": "refund"},
        {},
    ],
    ids=["amount", "currency", "price", "unknown-result", "empty"],
)
async def test_client_cannot_control_price_or_send_invalid_body(
    api_client, database_engine, paid_booking_setup, body
):
    booking_id, token = paid_booking_setup

    response = await api_client.post(
        mock_path(booking_id), json=body, headers=headers_for(token, _key())
    )

    assert response.status_code == 422
    assert payment_count(database_engine) == 0
    assert booking_status(database_engine, booking_id) == BookingStatus.HELD


@pytest.mark.anyio
@pytest.mark.parametrize("key", [None, "short"], ids=["missing", "short"])
async def test_idempotency_key_is_required(api_client, database_engine, paid_booking_setup, key):
    booking_id, token = paid_booking_setup

    response = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers_for(token, key)
    )

    assert response.status_code == 422
    assert payment_count(database_engine) == 0


@pytest.mark.anyio
async def test_reusing_a_key_for_a_different_result_conflicts(
    api_client, database_engine, paid_booking_setup
):
    booking_id, token = paid_booking_setup
    headers = headers_for(token, _key())
    await api_client.post(mock_path(booking_id), json={"result": "failure"}, headers=headers)

    response = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Idempotency key was already used for a different request"
    assert booking_status(database_engine, booking_id) == BookingStatus.HELD


@pytest.mark.anyio
async def test_expired_hold_is_not_payable(api_client, database_engine, paid_booking_setup):
    booking_id, token = paid_booking_setup
    with Session(database_engine) as session, session.begin():
        session.execute(
            update(Booking)
            .where(Booking.id == booking_id)
            .values(hold_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )

    response = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers_for(token, _key())
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Booking is not available for payment"
    assert payment_count(database_engine) == 0
    assert booking_status(database_engine, booking_id) != BookingStatus.CONFIRMED


@pytest.mark.anyio
async def test_free_booking_returns_422(api_client, email_sender, database_engine, psychologist):
    booking_id, token = await create_client_booking(
        api_client, email_sender, database_engine, psychologist, price_minor=0
    )

    response = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers_for(token, _key())
    )

    assert response.status_code == 422
    assert payment_count(database_engine) == 0


# Development-only availability


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("app_env", "enabled"),
    [("production", None), ("production", False), ("development", False)],
    ids=["production-default", "production-disabled", "development-disabled"],
)
async def test_endpoint_is_hidden_when_mock_payments_are_disabled(
    api_client, database_engine, paid_booking_setup, monkeypatch, app_env, enabled
):
    booking_id, token = paid_booking_setup
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "mock_payments_enabled", enabled)

    authorized = await api_client.post(
        mock_path(booking_id), json={"result": "success"}, headers=headers_for(token, _key())
    )
    anonymous = await api_client.post(mock_path(booking_id), json={})

    assert authorized.status_code == 404
    assert anonymous.status_code == 404
    assert payment_count(database_engine) == 0
    assert booking_status(database_engine, booking_id) == BookingStatus.HELD


def test_mock_endpoint_is_not_published_in_openapi():
    assert not any("/payments" in path for path in app.openapi()["paths"])


@pytest.mark.parametrize(
    ("app_env", "enabled", "active"),
    [
        ("development", None, True),
        ("production", None, False),
        ("development", False, False),
        ("production", True, True),
    ],
)
def test_mock_payments_setting_resolution(monkeypatch, app_env, enabled, active):
    monkeypatch.setattr(settings, "app_env", app_env)
    monkeypatch.setattr(settings, "mock_payments_enabled", enabled)

    assert settings.mock_payments_active is active
