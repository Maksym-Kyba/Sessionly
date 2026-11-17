import hashlib
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from app.accounts.models import Psychologist
from app.availability.models import AvailabilitySlot
from app.booking.models import Booking, BookingIdempotencyKey, BookingStatus
from app.booking.schemas import PaymentResult
from app.booking import api as booking_api
from app.core.config import settings
from app.notifications.models import (
    BookingVerificationGrant,
    EmailVerificationToken,
)
from app.notifications.schemas import VerificationRequest
from app.notifications.email_sender import UnconfiguredEmailSender
from app.notifications.service import (
    InvalidVerificationToken,
    consume_email_verification,
    request_email_verification,
)
from app.main import app


def _add_future_slot(database_engine, psychologist_id, offset_minutes=0):
    starts_at = datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(days=3)
    starts_at += timedelta(minutes=offset_minutes)
    with Session(database_engine) as session, session.begin():
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
        return slot.id


def _key() -> str:
    return secrets.token_urlsafe(24)


async def _verification_grant(client, sender, psychologist, email="client@example.test"):
    response = await client.post(
        "/api/v1/email-verifications",
        json={"email": email, "psychologist_public_id": psychologist.public_id},
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert len(sender.messages) >= 1
    link = sender.messages[-1].verification_url
    raw_token = re.search(r"#token=([^&]+)$", link)
    assert raw_token is not None
    consume = await client.post(
        "/api/v1/email-verifications/consume",
        json={"token": raw_token.group(1), "psychologist_public_id": "client-controlled"},
    )
    assert consume.status_code == 200
    assert consume.json()["psychologist_public_id"] == psychologist.public_id
    return consume.json()["booking_verification_token"]


@pytest.mark.anyio
async def test_verification_consume_returns_server_scoped_psychologist_public_id(
    api_client, psychologist, email_sender
):
    await api_client.post(
        "/api/v1/email-verifications",
        json={"email": "client@example.test", "psychologist_public_id": psychologist.public_id},
    )
    raw_token = re.search(r"#token=([^&]+)$", email_sender.messages[-1].verification_url).group(1)

    response = await api_client.post(
        "/api/v1/email-verifications/consume",
        json={"token": raw_token, "psychologist_public_id": "attacker-controlled"},
    )

    assert response.status_code == 200
    assert response.json()["psychologist_public_id"] == psychologist.public_id
    assert response.json()["booking_verification_token"]
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_verified_client_can_create_hold_and_read_booking(
    api_client, database_engine, psychologist, email_sender
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    key = _key()
    response = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": key},
        json={"slot_id": str(slot_id), "booking_verification_token": grant},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "HELD"
    assert payload["client_access_token"]
    assert not payload["idempotent_replay"]
    created = datetime.fromisoformat(payload["created_at"])
    expiry = datetime.fromisoformat(payload["hold_expires_at"])
    assert expiry - created == timedelta(minutes=15)

    with Session(database_engine) as session:
        booking = session.get(Booking, payload["id"])
        assert booking is not None
        assert booking.client_email == "client@example.test"
        assert booking.client_access_token_hash != payload["client_access_token"]
        assert booking.price_minor == 120000
        assert booking.currency == "UAH"

    unauthorized = await api_client.get(f"/api/v1/bookings/{payload['id']}")
    assert unauthorized.status_code == 401
    read = await api_client.get(
        f"/api/v1/bookings/{payload['id']}",
        headers={"Authorization": f"Bearer {payload['client_access_token']}"},
    )
    assert read.status_code == 200
    assert read.json()["id"] == payload["id"]
    assert "client_email" not in read.json()
    assert read.headers["cache-control"] == "no-store"


@pytest.mark.anyio
async def test_authenticated_psychologist_can_read_owned_booking(
    authenticated_client, database_engine, psychologist
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    with Session(database_engine) as session:
        booking = booking_api.create_hold(session, slot_id)
    response = await authenticated_client.get(f"/api/v1/bookings/{booking.id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(booking.id)


@pytest.mark.anyio
async def test_email_verification_is_generic_and_rate_limited(
    api_client, psychologist, email_sender
):
    unknown = await api_client.post(
        "/api/v1/email-verifications",
        json={"email": "client@example.test", "psychologist_public_id": "missing-psychologist"},
    )
    assert unknown.status_code == 202
    assert unknown.json() == {"status": "accepted"}
    assert email_sender.messages == []

    for _ in range(settings.client_verification_email_limit_per_hour + 1):
        response = await api_client.post(
            "/api/v1/email-verifications",
            json={
                "email": "client@example.test",
                "psychologist_public_id": psychologist.public_id,
            },
        )
        assert response.status_code == 202
        assert response.json() == {"status": "accepted"}
    assert len(email_sender.messages) == settings.client_verification_email_limit_per_hour


@pytest.mark.anyio
async def test_unconfigured_email_sender_fails_closed_and_keeps_committed_token(
    api_client, database_engine, psychologist, monkeypatch
):
    monkeypatch.setattr(app.state, "email_sender", UnconfiguredEmailSender())
    response = await api_client.post(
        "/api/v1/email-verifications",
        json={
            "email": "client@example.test",
            "psychologist_public_id": psychologist.public_id,
        },
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Email delivery is temporarily unavailable"}
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(EmailVerificationToken)) == 1


def test_concurrent_verification_requests_keep_each_unexpired_link_usable(
    database_engine, psychologist, email_sender
):
    barrier = Barrier(2)
    request = VerificationRequest(
        email="concurrent@example.test", psychologist_public_id=psychologist.public_id
    )

    def send_link():
        with Session(database_engine) as session:
            barrier.wait(timeout=5)
            request_email_verification(session, request, email_sender)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _: send_link(), range(2)))

    with Session(database_engine) as session:
        active_tokens = session.scalars(
            select(EmailVerificationToken).where(
                EmailVerificationToken.psychologist_id == psychologist.id,
                EmailVerificationToken.email == "concurrent@example.test",
                EmailVerificationToken.consumed_at.is_(None),
            )
        ).all()
    assert len(email_sender.messages) == 2
    assert len(active_tokens) == 2
    active_hashes = {token.token_hash for token in active_tokens}
    sent_hashes = {
        hashlib.sha256(
            re.search(r"#token=([^&]+)$", message.verification_url).group(1).encode()
        ).hexdigest()
        for message in email_sender.messages
    }
    assert active_hashes == sent_hashes


@pytest.mark.anyio
async def test_email_sender_runs_after_database_locks_are_released(
    api_client, database_engine, psychologist, monkeypatch
):
    class LockCheckingSender:
        lock_acquired = False
        token_was_committed = False

        def send_verification(self, recipient: str, verification_url: str) -> None:
            with Session(database_engine) as session, session.begin():
                session.execute(text("SET LOCAL lock_timeout = '250ms'"))
                session.scalar(
                    select(Psychologist).where(Psychologist.id == psychologist.id).with_for_update()
                )
                self.lock_acquired = True
                self.token_was_committed = (
                    session.scalar(
                        select(func.count())
                        .select_from(EmailVerificationToken)
                        .where(EmailVerificationToken.email == recipient)
                    )
                    == 1
                )

    sender = LockCheckingSender()
    monkeypatch.setattr(app.state, "email_sender", sender)
    response = await api_client.post(
        "/api/v1/email-verifications",
        json={
            "email": "lock-check@example.test",
            "psychologist_public_id": psychologist.public_id,
        },
    )

    assert response.status_code == 202
    assert sender.lock_acquired
    assert sender.token_was_committed


class AcceptThenTimeoutSender:
    def __init__(self) -> None:
        self.verification_url: str | None = None

    def send_verification(self, recipient: str, verification_url: str) -> None:
        self.verification_url = verification_url
        raise TimeoutError("simulated timeout after SMTP accepted the message")


@pytest.mark.anyio
async def test_ambiguous_smtp_timeout_leaves_delivered_verification_link_usable(
    api_client, psychologist, monkeypatch
):
    sender = AcceptThenTimeoutSender()
    monkeypatch.setattr(app.state, "email_sender", sender)
    requested = await api_client.post(
        "/api/v1/email-verifications",
        json={"email": "timeout@example.test", "psychologist_public_id": psychologist.public_id},
    )
    assert requested.status_code == 503
    assert sender.verification_url is not None

    raw_token = re.search(r"#token=([^&]+)$", sender.verification_url).group(1)
    consumed = await api_client.post(
        "/api/v1/email-verifications/consume", json={"token": raw_token}
    )
    assert consumed.status_code == 200
    assert consumed.json()["psychologist_public_id"] == psychologist.public_id


@pytest.mark.anyio
async def test_consuming_one_link_invalidates_all_sibling_links(
    api_client, database_engine, psychologist, email_sender
):
    request = {
        "email": "siblings@example.test",
        "psychologist_public_id": psychologist.public_id,
    }
    for _ in range(2):
        assert (
            await api_client.post("/api/v1/email-verifications", json=request)
        ).status_code == 202

    raw_tokens = [
        re.search(r"#token=([^&]+)$", message.verification_url).group(1)
        for message in email_sender.messages
    ]
    consumed = await api_client.post(
        "/api/v1/email-verifications/consume", json={"token": raw_tokens[0]}
    )
    sibling_replay = await api_client.post(
        "/api/v1/email-verifications/consume", json={"token": raw_tokens[1]}
    )

    assert consumed.status_code == 200
    assert sibling_replay.status_code == 400
    assert sibling_replay.json() == {"detail": "Verification link is invalid or expired"}
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(BookingVerificationGrant)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(EmailVerificationToken)
                .where(EmailVerificationToken.consumed_at.is_not(None))
            )
            == 2
        )


def test_concurrent_sibling_link_consumption_creates_one_grant(
    database_engine, psychologist, email_sender
):
    request = VerificationRequest(
        email="concurrent-consume@example.test", psychologist_public_id=psychologist.public_id
    )
    for _ in range(2):
        with Session(database_engine) as session:
            request_email_verification(session, request, email_sender)
    raw_tokens = [
        re.search(r"#token=([^&]+)$", message.verification_url).group(1)
        for message in email_sender.messages
    ]
    barrier = Barrier(2)

    def consume(raw_token: str) -> str:
        with Session(database_engine) as session:
            barrier.wait(timeout=5)
            try:
                consume_email_verification(session, raw_token)
            except InvalidVerificationToken:
                return "invalid"
            return "consumed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(consume, raw_tokens))

    assert sorted(results) == ["consumed", "invalid"]
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(BookingVerificationGrant)) == 1


@pytest.mark.anyio
async def test_verification_link_is_single_use_and_expired_links_fail(
    api_client, database_engine, psychologist, email_sender
):
    await _verification_grant(api_client, email_sender, psychologist)
    raw_link_token = re.search(
        r"#token=([^&]+)$", email_sender.messages[-1].verification_url
    ).group(1)
    replay = await api_client.post(
        "/api/v1/email-verifications/consume", json={"token": raw_link_token}
    )
    assert replay.status_code == 400
    assert replay.json() == {"detail": "Verification link is invalid or expired"}
    assert "psychologist_public_id" not in replay.json()

    invalid = await api_client.post("/api/v1/email-verifications/consume", json={"token": _key()})
    assert invalid.status_code == 400
    assert invalid.json() == {"detail": "Verification link is invalid or expired"}
    assert "psychologist_public_id" not in invalid.json()

    await api_client.post(
        "/api/v1/email-verifications",
        json={"email": "expired@example.test", "psychologist_public_id": psychologist.public_id},
    )
    expired_raw_token = re.search(
        r"#token=([^&]+)$", email_sender.messages[-1].verification_url
    ).group(1)
    with Session(database_engine) as session, session.begin():
        session.execute(
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.token_hash
                == hashlib.sha256(expired_raw_token.encode()).hexdigest()
            )
            .values(expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    expired = await api_client.post(
        "/api/v1/email-verifications/consume", json={"token": expired_raw_token}
    )
    assert expired.status_code == 400
    assert expired.json() == {"detail": "Verification link is invalid or expired"}
    assert "psychologist_public_id" not in expired.json()


@pytest.mark.anyio
async def test_verification_consumption_has_persisted_global_rate_limit(
    api_client, psychologist, email_sender, monkeypatch
):
    monkeypatch.setattr(settings, "client_verification_consume_limit_per_minute", 1)
    await api_client.post(
        "/api/v1/email-verifications",
        json={"email": "first@example.test", "psychologist_public_id": psychologist.public_id},
    )
    first_token = re.search(r"#token=([^&]+)$", email_sender.messages[-1].verification_url).group(1)
    first = await api_client.post(
        "/api/v1/email-verifications/consume", json={"token": first_token}
    )
    assert first.status_code == 200

    await api_client.post(
        "/api/v1/email-verifications",
        json={"email": "second@example.test", "psychologist_public_id": psychologist.public_id},
    )
    second_token = re.search(r"#token=([^&]+)$", email_sender.messages[-1].verification_url).group(
        1
    )
    second = await api_client.post(
        "/api/v1/email-verifications/consume", json={"token": second_token}
    )
    assert second.status_code == 429
    assert second.headers["retry-after"] == "60"


@pytest.mark.anyio
async def test_unverified_client_cannot_create_or_read_booking(
    api_client, database_engine, psychologist
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    response = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": _key()},
        json={"slot_id": str(slot_id), "booking_verification_token": _key()},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Booking verification is invalid or expired"
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(Booking)) == 0


@pytest.mark.anyio
async def test_booking_verification_grant_is_single_use(
    api_client, database_engine, psychologist, email_sender
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    first = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": _key()},
        json={"slot_id": str(slot_id), "booking_verification_token": grant},
    )
    assert first.status_code == 201
    reuse = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": _key()},
        json={"slot_id": str(slot_id), "booking_verification_token": grant},
    )
    assert reuse.status_code == 400
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(Booking)) == 1


@pytest.mark.anyio
async def test_idempotent_retry_returns_same_booking_without_reissuing_raw_token(
    api_client, database_engine, psychologist, email_sender
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    key = _key()
    body = {"slot_id": str(slot_id), "booking_verification_token": grant}
    first = await api_client.post("/api/v1/bookings", headers={"Idempotency-Key": key}, json=body)
    retry = await api_client.post("/api/v1/bookings", headers={"Idempotency-Key": key}, json=body)
    assert first.status_code == 201 and retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]
    assert retry.json()["idempotent_replay"] is True
    assert retry.json()["client_access_token"] is None
    assert retry.json()["hold_expires_at"] == first.json()["hold_expires_at"]
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(Booking)) == 1
        assert session.scalar(select(func.count()).select_from(BookingIdempotencyKey)) == 1


@pytest.mark.anyio
async def test_expired_grant_cannot_replay_idempotency_but_fresh_same_email_can_recover(
    api_client, database_engine, psychologist, email_sender
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    key = _key()
    body = {"slot_id": str(slot_id), "booking_verification_token": grant}
    first = await api_client.post("/api/v1/bookings", headers={"Idempotency-Key": key}, json=body)
    booking_id = first.json()["id"]
    old_access_token = first.json()["client_access_token"]
    with Session(database_engine) as session, session.begin():
        session.execute(
            update(BookingVerificationGrant)
            .where(
                BookingVerificationGrant.token_hash == hashlib.sha256(grant.encode()).hexdigest()
            )
            .values(expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    stale_replay = await api_client.post(
        "/api/v1/bookings", headers={"Idempotency-Key": key}, json=body
    )
    assert stale_replay.status_code == 400

    fresh_grant = await _verification_grant(api_client, email_sender, psychologist)
    replay = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": key},
        json={"slot_id": str(slot_id), "booking_verification_token": fresh_grant},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == booking_id
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["client_access_token"]
    assert replay.json()["client_access_token"] != old_access_token
    assert replay.json()["hold_expires_at"] == first.json()["hold_expires_at"]
    assert (
        await api_client.get(
            f"/api/v1/bookings/{booking_id}",
            headers={"Authorization": f"Bearer {replay.json()['client_access_token']}"},
        )
    ).status_code == 200


@pytest.mark.anyio
async def test_idempotency_key_cannot_be_reused_for_another_slot(
    api_client, database_engine, psychologist, email_sender
):
    first_slot = _add_future_slot(database_engine, psychologist.id)
    second_slot = _add_future_slot(database_engine, psychologist.id, offset_minutes=50)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    key = _key()
    first = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": key},
        json={"slot_id": str(first_slot), "booking_verification_token": grant},
    )
    assert first.status_code == 201
    mismatch = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": key},
        json={"slot_id": str(second_slot), "booking_verification_token": grant},
    )
    assert mismatch.status_code == 409


@pytest.mark.anyio
async def test_reverification_recovers_access_token_and_revokes_previous_token(
    api_client, database_engine, psychologist, email_sender
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    created = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": _key()},
        json={"slot_id": str(slot_id), "booking_verification_token": grant},
    )
    booking_id = created.json()["id"]
    old_token = created.json()["client_access_token"]

    recovery_grant = await _verification_grant(api_client, email_sender, psychologist)
    recovered = await api_client.post(
        f"/api/v1/bookings/{booking_id}/access-token",
        json={"booking_verification_token": recovery_grant},
    )
    assert recovered.status_code == 200
    new_token = recovered.json()["client_access_token"]
    assert new_token != old_token
    assert (
        await api_client.get(
            f"/api/v1/bookings/{booking_id}",
            headers={"Authorization": f"Bearer {old_token}"},
        )
    ).status_code == 404
    assert (
        await api_client.get(
            f"/api/v1/bookings/{booking_id}",
            headers={"Authorization": f"Bearer {new_token}"},
        )
    ).status_code == 200


@pytest.mark.anyio
async def test_expired_client_access_token_is_rejected(
    api_client, database_engine, psychologist, email_sender
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    created = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": _key()},
        json={"slot_id": str(slot_id), "booking_verification_token": grant},
    )
    booking_id = created.json()["id"]
    token = created.json()["client_access_token"]
    with Session(database_engine) as session, session.begin():
        booking = session.get(Booking, booking_id)
        booking.client_access_token_expires_at = func.clock_timestamp() - timedelta(seconds=1)
    response = await api_client.get(
        f"/api/v1/bookings/{booking_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 404


@pytest.mark.anyio
async def test_recovery_requires_same_verified_email_and_psychologist(
    api_client, database_engine, psychologist, email_sender
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    created = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": _key()},
        json={"slot_id": str(slot_id), "booking_verification_token": grant},
    )
    wrong_grant = await _verification_grant(
        api_client, email_sender, psychologist, email="other@example.test"
    )
    recovered = await api_client.post(
        f"/api/v1/bookings/{created.json()['id']}/access-token",
        json={"booking_verification_token": wrong_grant},
    )
    assert recovered.status_code == 400


@pytest.mark.anyio
async def test_expired_hold_is_not_revived_by_idempotent_retry_or_access(
    api_client, database_engine, psychologist, email_sender
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    key = _key()
    body = {"slot_id": str(slot_id), "booking_verification_token": grant}
    created = await api_client.post("/api/v1/bookings", headers={"Idempotency-Key": key}, json=body)
    booking_id = created.json()["id"]
    token = created.json()["client_access_token"]
    with Session(database_engine) as session, session.begin():
        booking = session.get(Booking, booking_id)
        booking.hold_expires_at = func.clock_timestamp() - timedelta(seconds=1)
        session.flush()
        session.refresh(booking)
        expired_deadline = booking.hold_expires_at
    retry = await api_client.post("/api/v1/bookings", headers={"Idempotency-Key": key}, json=body)
    assert retry.status_code == 200
    assert retry.json()["id"] == booking_id
    assert retry.json()["status"] == BookingStatus.EXPIRED
    assert datetime.fromisoformat(retry.json()["hold_expires_at"]) == expired_deadline
    read = await api_client.get(
        f"/api/v1/bookings/{booking_id}", headers={"Authorization": f"Bearer {token}"}
    )
    assert read.status_code == 200
    assert read.json()["status"] == BookingStatus.EXPIRED


@pytest.mark.anyio
async def test_concurrent_same_idempotency_request_creates_one_booking(
    api_client, database_engine, psychologist, email_sender
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    key = _key()
    barrier = Barrier(2)

    def create():
        with Session(database_engine) as session:
            barrier.wait(timeout=5)
            result = booking_api.create_verified_hold(session, slot_id, grant, key)
            return result.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))
    assert results[0] == results[1]
    with Session(database_engine) as session:
        assert session.scalar(select(func.count()).select_from(Booking)) == 1
        assert session.scalar(select(func.count()).select_from(BookingIdempotencyKey)) == 1


@pytest.mark.anyio
async def test_payment_api_remains_internal_and_late_confirmation_stays_expired(
    api_client, database_engine, psychologist, email_sender
):
    slot_id = _add_future_slot(database_engine, psychologist.id)
    grant = await _verification_grant(api_client, email_sender, psychologist)
    created = await api_client.post(
        "/api/v1/bookings",
        headers={"Idempotency-Key": _key()},
        json={"slot_id": str(slot_id), "booking_verification_token": grant},
    )
    booking_id = created.json()["id"]
    assert (await api_client.post(f"/api/v1/bookings/{booking_id}/confirm")).status_code == 404
    with Session(database_engine) as session, session.begin():
        booking = session.get(Booking, booking_id)
        booking.hold_expires_at = func.clock_timestamp() - timedelta(seconds=1)
    with Session(database_engine) as session:
        outcome = booking_api.confirm_held_booking(
            session,
            booking_id,
            PaymentResult(payment_reference="late-payment", succeeded=True),
        )
    assert outcome.value == "EXPIRED"
    public_paths = app.openapi()["paths"]
    assert not any("/payments" in path or "/confirm" in path for path in public_paths)
