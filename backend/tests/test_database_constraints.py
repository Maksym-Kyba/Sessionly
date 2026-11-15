from datetime import date, datetime, time, timedelta, timezone

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.accounts.models import Psychologist
from app.availability.models import AvailabilityRule, AvailabilitySlot


def test_migration_enforces_rule_checks(database_engine, psychologist):
    invalid_rule = AvailabilityRule(
        psychologist_id=psychologist.id,
        weekday=7,
        local_start=time(9),
        local_end=time(10),
        session_duration_minutes=60,
        price_minor=10000,
        currency="UAH",
        valid_from=date.today(),
    )

    with pytest.raises(IntegrityError), Session(database_engine) as session:
        with session.begin():
            session.add(invalid_rule)
            session.flush()


def test_migration_prevents_duplicate_materialized_slots(database_engine, psychologist):
    now = datetime.now(timezone.utc)
    first = AvailabilitySlot(
        psychologist_id=psychologist.id,
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, minutes=50),
        price_minor=10000,
        currency="UAH",
    )
    duplicate = AvailabilitySlot(
        psychologist_id=psychologist.id,
        starts_at=first.starts_at,
        ends_at=first.ends_at,
        price_minor=10000,
        currency="UAH",
    )

    with pytest.raises(IntegrityError), Session(database_engine) as session:
        with session.begin():
            session.add_all([first, duplicate])
            session.flush()


def test_migration_restricts_initial_currency_to_uah(database_engine, psychologist):
    now = datetime.now(timezone.utc)
    unsupported_slot = AvailabilitySlot(
        psychologist_id=psychologist.id,
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=1, minutes=50),
        price_minor=10000,
        currency="USD",
    )

    with pytest.raises(IntegrityError), Session(database_engine) as session:
        with session.begin():
            session.add(unsupported_slot)
            session.flush()


def test_foreign_key_restricts_deleting_a_psychologist_with_rules(
    database_engine, psychologist
):
    rule = AvailabilityRule(
        psychologist_id=psychologist.id,
        weekday=0,
        local_start=time(9),
        local_end=time(10),
        session_duration_minutes=60,
        price_minor=10000,
        currency="UAH",
        valid_from=date.today(),
    )
    with Session(database_engine) as session, session.begin():
        session.add(rule)

    with pytest.raises(IntegrityError), Session(database_engine) as session:
        with session.begin():
            session.execute(
                delete(Psychologist).where(Psychologist.id == psychologist.id)
            )
            session.flush()
