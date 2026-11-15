from datetime import datetime, timezone
from typing import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.availability.models import AvailabilityRule, AvailabilitySlot


def list_rules(session: Session, psychologist_id: UUID) -> list[AvailabilityRule]:
    statement = (
        select(AvailabilityRule)
        .where(AvailabilityRule.psychologist_id == psychologist_id)
        .order_by(AvailabilityRule.weekday, AvailabilityRule.local_start, AvailabilityRule.id)
    )
    return list(session.scalars(statement))


def list_active_rules(session: Session, psychologist_id: UUID) -> list[AvailabilityRule]:
    statement = select(AvailabilityRule).where(
        AvailabilityRule.psychologist_id == psychologist_id,
        AvailabilityRule.is_active.is_(True),
    )
    return list(session.scalars(statement))


def add_rule(session: Session, psychologist_id: UUID, values: dict) -> AvailabilityRule:
    rule = AvailabilityRule(psychologist_id=psychologist_id, **values)
    session.add(rule)
    session.flush()
    return rule


def update_rule_fields(
    session: Session, rule: AvailabilityRule, values: dict
) -> AvailabilityRule:
    for name, value in values.items():
        setattr(rule, name, value)
    session.flush()
    return rule


def retire_rule_record(session: Session, rule: AvailabilityRule) -> None:
    rule.is_active = False
    session.flush()


def get_rule(
    session: Session, psychologist_id: UUID, rule_id: UUID, *, lock: bool = False
) -> AvailabilityRule | None:
    statement = select(AvailabilityRule).where(
        AvailabilityRule.psychologist_id == psychologist_id,
        AvailabilityRule.id == rule_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def slots_for_reconciliation(
    session: Session, psychologist_id: UUID, from_time: datetime
) -> list[AvailabilitySlot]:
    statement = select(AvailabilitySlot).where(
        AvailabilitySlot.psychologist_id == psychologist_id,
        AvailabilitySlot.starts_at >= from_time,
    )
    return list(session.scalars(statement))


def reconcile_slots(
    session: Session,
    psychologist_id: UUID,
    from_time: datetime,
    desired: Mapping[tuple[datetime, datetime], tuple[AvailabilityRule, int, str]],
) -> None:
    existing_slots = slots_for_reconciliation(session, psychologist_id, from_time)
    existing_by_key = {
        (slot.starts_at.astimezone(timezone.utc), slot.ends_at.astimezone(timezone.utc)): slot
        for slot in existing_slots
    }

    for key, (rule, price_minor, currency) in desired.items():
        slot = existing_by_key.get(key)
        if slot is None:
            session.add(
                AvailabilitySlot(
                    psychologist_id=psychologist_id,
                    availability_rule_id=rule.id,
                    starts_at=key[0],
                    ends_at=key[1],
                    price_minor=price_minor,
                    currency=currency,
                    state="published",
                )
            )
        else:
            slot.availability_rule_id = rule.id
            slot.price_minor = price_minor
            slot.currency = currency
            slot.state = "published"

    for key, slot in existing_by_key.items():
        if key not in desired:
            slot.state = "withdrawn"
    session.flush()


def list_published_slots(
    session: Session, psychologist_id: UUID, from_time: datetime, to_time: datetime
) -> list[AvailabilitySlot]:
    statement = (
        select(AvailabilitySlot)
        .where(
            AvailabilitySlot.psychologist_id == psychologist_id,
            AvailabilitySlot.state == "published",
            AvailabilitySlot.starts_at >= from_time,
            AvailabilitySlot.starts_at < to_time,
        )
        .order_by(AvailabilitySlot.starts_at)
    )
    return list(session.scalars(statement))
