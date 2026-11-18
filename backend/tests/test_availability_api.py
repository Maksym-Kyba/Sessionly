import asyncio
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.accounts.dependencies import get_current_psychologist_id
from app.accounts.models import Psychologist
from app.availability.models import AvailabilityRule, AvailabilitySlot
from app.main import app


def _rule_payload(target_day: date) -> dict[str, object]:
    return {
        "weekday": target_day.weekday(),
        "local_start": "10:00:00",
        "local_end": "12:00:00",
        "session_duration_minutes": 60,
        "price_minor": 150000,
        "currency": "UAH",
        "valid_from": target_day.isoformat(),
        "valid_until": target_day.isoformat(),
    }


def _target_day() -> date:
    return date.today() + timedelta(days=2)


def _availability_url(public_id: str, target_day: date) -> str:
    local_start = datetime.combine(target_day, datetime.min.time()).replace(hour=0)
    from_time = local_start.replace(tzinfo=timezone.utc) - timedelta(days=1)
    to_time = from_time + timedelta(days=30)
    from_query = from_time.isoformat().replace("+00:00", "Z")
    to_query = to_time.isoformat().replace("+00:00", "Z")
    return (
        f"/api/v1/psychologists/{public_id}/availability"
        f"?from={from_query}&to={to_query}"
    )


@pytest.mark.anyio
async def test_protected_rule_endpoints_fail_closed_without_authentication(authenticated_client):
    app.dependency_overrides.pop(get_current_psychologist_id)

    response = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules",
        json=_rule_payload(_target_day()),
        headers={"Authorization": "Bearer unverified-token"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.anyio
async def test_create_list_update_retire_and_publicly_list_slots(
    authenticated_client, psychologist, database_engine
):
    target_day = _target_day()
    payload = _rule_payload(target_day)
    create_response = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules", json=payload
    )
    assert create_response.status_code == 201, create_response.text
    created_rule = create_response.json()
    assert created_rule["currency"] == "UAH"
    assert created_rule["price_minor"] == 150000

    listing = await authenticated_client.get("/api/v1/accounts/me/availability-rules")
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    public_response = await authenticated_client.get(
        _availability_url(psychologist.public_id, target_day)
    )
    assert public_response.status_code == 200, public_response.text
    public_data = public_response.json()
    assert public_data["time_zone"] == "Europe/Kyiv"
    assert len(public_data["slots"]) == 2
    assert {slot["price_minor"] for slot in public_data["slots"]} == {150000}
    assert {slot["currency"] for slot in public_data["slots"]} == {"UAH"}
    assert {slot["state"] for slot in public_data["slots"]} == {"available"}

    updated_payload = {**payload, "price_minor": 180000, "session_duration_minutes": 30}
    update_response = await authenticated_client.put(
        f"/api/v1/accounts/me/availability-rules/{created_rule['id']}",
        json=updated_payload,
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["price_minor"] == 180000

    public_after_update = await authenticated_client.get(
        _availability_url(psychologist.public_id, target_day)
    )
    assert len(public_after_update.json()["slots"]) == 4
    assert {slot["price_minor"] for slot in public_after_update.json()["slots"]} == {180000}
    with database_engine.connect() as connection:
        updated_slot_states = connection.execute(
            select(AvailabilitySlot.state).where(
                AvailabilitySlot.psychologist_id == psychologist.id
            )
        ).scalars().all()
    assert updated_slot_states.count("withdrawn") == 2
    assert updated_slot_states.count("published") == 4

    delete_response = await authenticated_client.delete(
        f"/api/v1/accounts/me/availability-rules/{created_rule['id']}"
    )
    assert delete_response.status_code == 204

    with database_engine.connect() as connection:
        retired_rule = connection.execute(
            select(AvailabilityRule.is_active).where(
                AvailabilityRule.id == UUID(created_rule["id"])
            )
        ).scalar_one()
        slot_states = connection.execute(
            select(AvailabilitySlot.state).where(
                AvailabilitySlot.psychologist_id == psychologist.id
            )
        ).scalars().all()
    assert retired_rule is False
    assert len(slot_states) == 6
    assert set(slot_states) == {"withdrawn"}

    assert (await authenticated_client.get(
        _availability_url(psychologist.public_id, target_day)
    )).json()["slots"] == []


@pytest.mark.anyio
async def test_invalid_rule_and_missing_public_psychologist_return_errors(authenticated_client):
    payload = _rule_payload(_target_day())
    payload["local_end"] = "09:00:00"
    assert (await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules", json=payload
    )).status_code == 422

    response = await authenticated_client.get(
        _availability_url("does-not-exist", _target_day())
    )
    assert response.status_code == 404

@pytest.mark.anyio
async def test_overlapping_future_rules_are_rejected_even_outside_slot_horizon(
    authenticated_client,
):
    future_day = date.today() + timedelta(days=45)
    first = _rule_payload(future_day)
    first["valid_until"] = None
    first_response = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules", json=first
    )
    assert first_response.status_code == 201, first_response.text

    overlapping = {
        **first,
        "local_start": "11:00:00",
        "local_end": "13:00:00",
        "price_minor": 150000,
    }
    second_response = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules", json=overlapping
    )
    assert second_response.status_code == 409
    assert len((await authenticated_client.get(
        "/api/v1/accounts/me/availability-rules"
    )).json()) == 1


@pytest.mark.anyio
async def test_rule_cannot_have_a_session_longer_than_its_window(authenticated_client):
    payload = _rule_payload(_target_day())
    payload["session_duration_minutes"] = 121

    response = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules", json=payload
    )

    assert response.status_code == 422

    unsupported_currency = _rule_payload(_target_day())
    unsupported_currency["currency"] = "USD"
    assert (
        await authenticated_client.post(
            "/api/v1/accounts/me/availability-rules", json=unsupported_currency
        )
    ).status_code == 422


@pytest.mark.anyio
async def test_break_between_sessions_spaces_out_slots(authenticated_client, psychologist):
    target_day = _target_day()
    payload = _rule_payload(target_day)
    payload.update(session_duration_minutes=50, break_minutes=10)
    response = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules", json=payload
    )
    assert response.status_code == 201, response.text
    assert response.json()["break_minutes"] == 10

    slots = (await authenticated_client.get(
        _availability_url(psychologist.public_id, target_day)
    )).json()["slots"]
    starts = [datetime.fromisoformat(slot["starts_at"]) for slot in slots]
    ends = [datetime.fromisoformat(slot["ends_at"]) for slot in slots]
    assert len(slots) == 2
    assert all(end - start == timedelta(minutes=50) for start, end in zip(starts, ends))
    assert starts[1] - starts[0] == timedelta(minutes=60)


@pytest.mark.anyio
async def test_break_defaults_to_zero_and_rejects_invalid_values(
    authenticated_client, psychologist
):
    target_day = _target_day()
    payload = _rule_payload(target_day)
    payload["session_duration_minutes"] = 50
    response = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules", json=payload
    )
    assert response.status_code == 201, response.text
    assert response.json()["break_minutes"] == 0

    slots = (await authenticated_client.get(
        _availability_url(psychologist.public_id, target_day)
    )).json()["slots"]
    starts = [datetime.fromisoformat(slot["starts_at"]) for slot in slots]
    assert starts[1] - starts[0] == timedelta(minutes=50)

    for invalid in (-1, 241):
        invalid_payload = {**_rule_payload(target_day), "break_minutes": invalid}
        assert (await authenticated_client.post(
            "/api/v1/accounts/me/availability-rules", json=invalid_payload
        )).status_code == 422


@pytest.mark.anyio
async def test_update_without_break_keeps_it_and_explicit_zero_resets_it(authenticated_client):
    payload = {**_rule_payload(_target_day()), "session_duration_minutes": 50, "break_minutes": 10}
    created = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules", json=payload
    )
    assert created.status_code == 201, created.text
    rule_url = f"/api/v1/accounts/me/availability-rules/{created.json()['id']}"

    legacy_payload = {key: value for key, value in payload.items() if key != "break_minutes"}
    legacy_payload["price_minor"] = 160000
    kept = await authenticated_client.put(rule_url, json=legacy_payload)
    assert kept.status_code == 200, kept.text
    assert kept.json()["break_minutes"] == 10
    assert kept.json()["price_minor"] == 160000

    reset = await authenticated_client.put(rule_url, json={**legacy_payload, "break_minutes": 0})
    assert reset.status_code == 200, reset.text
    assert reset.json()["break_minutes"] == 0


@pytest.mark.anyio
async def test_conflicting_update_rolls_back_rule_and_slot_changes(
    authenticated_client, psychologist
):
    target_day = _target_day()
    first = _rule_payload(target_day)
    first.update(local_start="09:00:00", local_end="10:00:00")
    second = _rule_payload(target_day)
    second.update(local_start="11:00:00", local_end="12:00:00")

    first_response = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules", json=first
    )
    second_response = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules", json=second
    )
    assert first_response.status_code == 201
    assert second_response.status_code == 201

    conflicting_update = {
        **second,
        "local_start": "09:30:00",
        "local_end": "10:30:00",
    }
    response = await authenticated_client.put(
        f"/api/v1/accounts/me/availability-rules/{second_response.json()['id']}",
        json=conflicting_update,
    )
    assert response.status_code == 409

    listed_rules = await authenticated_client.get(
        "/api/v1/accounts/me/availability-rules"
    )
    assert {rule["local_start"] for rule in listed_rules.json()} == {
        "09:00:00",
        "11:00:00",
    }
    availability = await authenticated_client.get(
        _availability_url(psychologist.public_id, target_day)
    )
    assert len(availability.json()["slots"]) == 2


@pytest.mark.anyio
async def test_rule_operations_are_scoped_to_authenticated_psychologist(
    authenticated_client, psychologist, database_engine
):
    target_day = _target_day()
    own_rule = await authenticated_client.post(
        "/api/v1/accounts/me/availability-rules",
        json=_rule_payload(target_day),
    )
    assert own_rule.status_code == 201

    with Session(database_engine) as session, session.begin():
        other = Psychologist(
            display_name="Other Psychologist",
            email="other@example.test",
            time_zone="Europe/Kyiv",
        )
        session.add(other)
        session.flush()
        other_id = other.id
    app.dependency_overrides[get_current_psychologist_id] = lambda: other_id

    update_response = await authenticated_client.put(
        f"/api/v1/accounts/me/availability-rules/{own_rule.json()['id']}",
        json=_rule_payload(target_day),
    )
    delete_response = await authenticated_client.delete(
        f"/api/v1/accounts/me/availability-rules/{own_rule.json()['id']}"
    )

    assert update_response.status_code == 404
    assert delete_response.status_code == 404


@pytest.mark.anyio
async def test_concurrent_duplicate_rules_materialize_unique_slots(authenticated_client, psychologist):
    target_day = _target_day()
    payload = _rule_payload(target_day)
    route = "/api/v1/accounts/me/availability-rules"

    responses = await asyncio.gather(
        *(authenticated_client.post(route, json=payload) for _ in range(2))
    )

    assert [response.status_code for response in responses] == [201, 201]
    public_response = await authenticated_client.get(
        _availability_url(psychologist.public_id, target_day)
    )
    assert public_response.status_code == 200
    assert len(public_response.json()["slots"]) == 2


@pytest.mark.anyio
async def test_concurrent_conflicting_future_rules_are_serialized(authenticated_client):
    future_day = date.today() + timedelta(days=45)
    first = _rule_payload(future_day)
    first["valid_until"] = None
    second = {
        **first,
        "local_start": "11:00:00",
        "local_end": "13:00:00",
    }

    responses = await asyncio.gather(
        authenticated_client.post("/api/v1/accounts/me/availability-rules", json=first),
        authenticated_client.post("/api/v1/accounts/me/availability-rules", json=second),
    )

    assert sorted(response.status_code for response in responses) == [201, 409]
