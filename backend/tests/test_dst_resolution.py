from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.availability.models import AvailabilityRule
from app.availability.service import _rule_occurrences, resolve_local_datetime


def _rule(day: date, start: time, end: time) -> AvailabilityRule:
    return AvailabilityRule(
        weekday=day.weekday(),
        local_start=start,
        local_end=end,
        session_duration_minutes=60,
        price_minor=10000,
        currency="UAH",
        valid_from=day,
    )


def test_nonexistent_local_time_is_skipped():
    local = datetime(2026, 3, 29, 3, 30)

    assert resolve_local_datetime(local, ZoneInfo("Europe/Kyiv")) is None


def test_ambiguous_local_time_uses_earlier_fold_as_proposed():
    local = datetime(2026, 10, 25, 3, 30)

    resolved = resolve_local_datetime(local, ZoneInfo("Europe/Kyiv"))

    assert resolved == datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)


def test_spring_transition_keeps_elapsed_session_lengths_and_skips_gap_starts():
    transition_day = date(2026, 3, 29)
    occurrences = list(
        _rule_occurrences(
            _rule(transition_day, time(1), time(4)),
            ZoneInfo("Europe/Berlin"),
            transition_day,
            transition_day + timedelta(days=1),
        )
    )

    assert occurrences == [
        (datetime(2026, 3, 29, 0, tzinfo=timezone.utc), datetime(2026, 3, 29, 1, tzinfo=timezone.utc)),
        (datetime(2026, 3, 29, 1, tzinfo=timezone.utc), datetime(2026, 3, 29, 2, tzinfo=timezone.utc)),
    ]


def test_fall_transition_uses_only_first_fold_and_never_changes_elapsed_duration():
    transition_day = date(2026, 10, 25)
    occurrences = list(
        _rule_occurrences(
            _rule(transition_day, time(1), time(4)),
            ZoneInfo("Europe/Berlin"),
            transition_day,
            transition_day + timedelta(days=1),
        )
    )

    assert [start for start, _ in occurrences] == [
        datetime(2026, 10, 24, 23, tzinfo=timezone.utc),
        datetime(2026, 10, 25, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 25, 2, tzinfo=timezone.utc),
    ]
    assert all(end - start == timedelta(minutes=60) for start, end in occurrences)


def test_nonexistent_rule_boundary_skips_that_date_occurrence():
    transition_day = date(2026, 3, 29)

    occurrences = list(
        _rule_occurrences(
            _rule(transition_day, time(1), time(2, 30)),
            ZoneInfo("Europe/Berlin"),
            transition_day,
            transition_day + timedelta(days=1),
        )
    )

    assert occurrences == []
