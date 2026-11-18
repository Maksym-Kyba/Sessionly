from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.accounts import api as accounts_api
from app.accounts.models import Psychologist
from app.availability import repository
from app.availability.models import AvailabilityRule, AvailabilitySlot
from app.availability.schemas import AvailabilityRuleInput

UTC = timezone.utc
MATERIALIZATION_DAYS = 30


class AvailabilityConflict(Exception):
    """Raised when active rules produce conflicting slot identities."""


def resolve_local_datetime(local_value: datetime, zone: ZoneInfo) -> datetime | None:
    """Resolve local wall time to UTC; skip gaps and choose fold 0 for ambiguous times.

    The fold-0 choice and gap-skipping behavior are implementation proposals because the project
    documents DST handling as unresolved. Keeping this policy in one helper makes it replaceable.
    """
    if local_value.tzinfo is not None:
        raise ValueError("Expected a naive local wall-clock datetime")

    candidate = local_value.replace(tzinfo=zone, fold=0)
    round_trip = candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None)
    if round_trip != local_value:
        return None
    return candidate.astimezone(UTC)


def _rule_occurrences(
    rule: AvailabilityRule, zone: ZoneInfo, start_date: date, end_date: date
) -> Iterable[tuple[datetime, datetime]]:
    day = start_date
    while day < end_date:
        if (
            day.weekday() == rule.weekday
            and day >= rule.valid_from
            and (rule.valid_until is None or day <= rule.valid_until)
        ):
            local_window_start = datetime.combine(day, rule.local_start)
            local_window_end = datetime.combine(day, rule.local_end)
            window_start_utc = resolve_local_datetime(local_window_start, zone)
            window_end_utc = resolve_local_datetime(local_window_end, zone)
            if window_start_utc is not None and window_end_utc is not None:
                local_start = local_window_start
                duration = timedelta(minutes=rule.session_duration_minutes)
                step = duration + timedelta(minutes=rule.break_minutes or 0)
                while local_start + duration <= local_window_end:
                    slot_start = resolve_local_datetime(local_start, zone)
                    if slot_start is not None:
                        slot_end = slot_start + duration
                        if slot_end <= window_end_utc:
                            yield slot_start, slot_end
                    local_start += step
        day += timedelta(days=1)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Availability query timestamps must include a timezone")
    return value.astimezone(UTC)


def _date_ranges_intersect(first: AvailabilityRule, second: AvailabilityRule) -> bool:
    latest_start = max(first.valid_from, second.valid_from)
    earliest_end = min(
        (end for end in (first.valid_until, second.valid_until) if end is not None),
        default=None,
    )
    first_common_weekday = latest_start + timedelta(
        days=(first.weekday - latest_start.weekday()) % 7
    )
    return earliest_end is None or first_common_weekday <= earliest_end


def _same_weekly_schedule(first: AvailabilityRule, second: AvailabilityRule) -> bool:
    return (
        first.weekday == second.weekday
        and first.local_start == second.local_start
        and first.local_end == second.local_end
        and first.session_duration_minutes == second.session_duration_minutes
        and first.break_minutes == second.break_minutes
        and first.price_minor == second.price_minor
        and first.currency == second.currency
    )


def _validate_rule_overlaps(
    active_rules: Iterable[AvailabilityRule], rule: AvailabilityRule
) -> None:
    for other in active_rules:
        if (
            other.id == rule.id
            or rule.weekday != other.weekday
            or not _date_ranges_intersect(rule, other)
        ):
            continue
        wall_times_overlap = (
            rule.local_start < other.local_end and other.local_start < rule.local_end
        )
        if wall_times_overlap and not _same_weekly_schedule(rule, other):
            raise AvailabilityConflict(
                "Availability rules overlap with different times, duration, break, or price"
            )


def _materialize(session: Session, psychologist_id: UUID) -> None:
    psychologist = accounts_api.psychologist_by_id(session, psychologist_id, lock=True)
    if psychologist is None:
        raise LookupError("Psychologist not found")
    try:
        zone = ZoneInfo(psychologist.time_zone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Psychologist has an invalid IANA time zone") from exc

    now = datetime.now(UTC)
    local_today = now.astimezone(zone).date()
    horizon_end = local_today + timedelta(days=MATERIALIZATION_DAYS)
    rules = repository.list_active_rules(session, psychologist_id)

    desired: dict[tuple[datetime, datetime], tuple[AvailabilityRule, int, str]] = {}
    for rule in rules:
        for starts_at, ends_at in _rule_occurrences(rule, zone, local_today, horizon_end):
            if starts_at < now:
                continue
            key = (starts_at, ends_at)
            prior = desired.get(key)
            value = (rule, rule.price_minor, rule.currency)
            if prior is not None and (prior[1], prior[2]) != (rule.price_minor, rule.currency):
                raise AvailabilityConflict("Overlapping rules define different prices for one slot")
            if prior is None:
                desired[key] = value

    ordered_slots = sorted(desired)
    for previous, current in zip(ordered_slots, ordered_slots[1:]):
        if current[0] < previous[1]:
            raise AvailabilityConflict("Availability rules generate overlapping appointment slots")

    repository.reconcile_slots(session, psychologist_id, now, desired)


def create_rule(
    session: Session, psychologist_id: UUID, data: AvailabilityRuleInput
) -> AvailabilityRule:
    with session.begin():
        if accounts_api.psychologist_by_id(session, psychologist_id, lock=True) is None:
            raise LookupError("Psychologist not found")
        rule = repository.add_rule(session, psychologist_id, data.model_dump())
        _validate_rule_overlaps(repository.list_active_rules(session, psychologist_id), rule)
        _materialize(session, psychologist_id)
        session.flush()
    return rule


def update_rule(
    session: Session, psychologist_id: UUID, rule_id: UUID, data: AvailabilityRuleInput
) -> AvailabilityRule | None:
    with session.begin():
        if accounts_api.psychologist_by_id(session, psychologist_id, lock=True) is None:
            return None
        rule = repository.get_rule(session, psychologist_id, rule_id, lock=True)
        if rule is None or not rule.is_active:
            return None
        repository.update_rule_fields(session, rule, data.model_dump())
        _validate_rule_overlaps(repository.list_active_rules(session, psychologist_id), rule)
        _materialize(session, psychologist_id)
        session.flush()
    return rule


def retire_rule(session: Session, psychologist_id: UUID, rule_id: UUID) -> bool:
    with session.begin():
        if accounts_api.psychologist_by_id(session, psychologist_id, lock=True) is None:
            return False
        rule = repository.get_rule(session, psychologist_id, rule_id, lock=True)
        if rule is None or not rule.is_active:
            return False
        repository.retire_rule_record(session, rule)
        _materialize(session, psychologist_id)
        session.flush()
    return True


def list_rules(session: Session, psychologist_id: UUID) -> list[AvailabilityRule]:
    return repository.list_rules(session, psychologist_id)


def refresh_slots(session: Session, psychologist_id: UUID) -> None:
    if session.in_transaction():
        _materialize(session, psychologist_id)
    else:
        with session.begin():
            _materialize(session, psychologist_id)


def public_slots(
    session: Session, public_id: str, from_time: datetime, to_time: datetime
) -> tuple[Psychologist, list[AvailabilitySlot]] | None:
    from_utc = _aware_utc(from_time)
    to_utc = _aware_utc(to_time)
    if to_utc <= from_utc:
        raise ValueError("to must be later than from")
    if to_utc - from_utc > timedelta(days=MATERIALIZATION_DAYS):
        raise ValueError("Availability queries may span at most 30 days")
    with session.begin():
        psychologist = accounts_api.psychologist_by_public_id(session, public_id)
        if psychologist is None:
            return None
        accounts_api.psychologist_by_id(session, psychologist.id, lock=True)
        _materialize(session, psychologist.id)
        slots = repository.list_published_slots(
            session, psychologist.id, max(from_utc, datetime.now(UTC)), to_utc
        )
    return psychologist, slots


def public_profile_terms(session: Session, psychologist_id: UUID) -> tuple[int, int, str] | None:
    return repository.public_profile_terms(session, psychologist_id, datetime.now(UTC))
