from datetime import UTC, datetime, timedelta
from itertools import islice
from zoneinfo import ZoneInfo

import pytest

from kqbot.events import DEFAULT_EVENTS, Event
from kqbot.schedule import current_occurrence, next_occurrence, occurrences

PACIFIC = ZoneInfo("America/Los_Angeles")
EVENTS = {e.key: e for e in DEFAULT_EVENTS}
HONEYING = EVENTS["honeying"]


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def starts(event: Event, after: datetime, count: int) -> list[datetime]:
    return [o.start for o in islice(occurrences(event, after, PACIFIC), count)]


def test_matches_observed_start():
    # Observed in game: Honeying started at 16:03 UTC on 2026-10-06 (09:03 PDT).
    assert next_occurrence(HONEYING, utc(2026, 10, 6, 15, 50), PACIFIC).start == utc(
        2026, 10, 6, 16, 3
    )


@pytest.mark.parametrize(
    ("key", "minute"),
    [("brigade", 0), ("robo", 1), ("honeying", 3), ("dragon", 9), ("pirates", 12)],
)
def test_each_event_runs_on_odd_pacific_hours_at_its_minute(key, minute):
    for start in starts(EVENTS[key], utc(2026, 10, 6), 24):
        local = start.astimezone(PACIFIC)
        assert local.hour % 2 == 1
        assert local.minute == minute


def test_every_two_hours():
    times = starts(HONEYING, utc(2026, 10, 6), 5)
    assert all(b - a == timedelta(hours=2) for a, b in zip(times, times[1:], strict=False))


def test_crosses_local_midnight():
    # 23:03 PDT on Oct 6 is 06:03 UTC Oct 7; the next one is 01:03 PDT Oct 7.
    after = utc(2026, 10, 7, 6, 5)
    nxt = next_occurrence(HONEYING, after, PACIFIC).start
    assert nxt == utc(2026, 10, 7, 8, 3)
    assert nxt.astimezone(PACIFIC).hour == 1


def test_start_exactly_now_is_not_next():
    now = utc(2026, 10, 6, 16, 3)
    assert next_occurrence(HONEYING, now, PACIFIC).start == utc(2026, 10, 6, 18, 3)


def test_standard_time_shifts_utc_by_an_hour():
    # After daylight saving ends, 09:03 PST is 17:03 UTC.
    assert next_occurrence(HONEYING, utc(2026, 11, 2, 16, 10), PACIFIC).start == utc(
        2026, 11, 2, 17, 3
    )


def test_fall_back_repeated_hour_counts_once():
    # Nov 1 2026: clocks go 01:59 PDT -> 01:00 PST, so 01:03 happens twice.
    # Expect 23:03 PDT, 01:03 PDT, then straight to 03:03 PST.
    assert starts(HONEYING, utc(2026, 11, 1, 6, 0), 3) == [
        utc(2026, 11, 1, 6, 3),  # Oct 31 23:03 PDT
        utc(2026, 11, 1, 8, 3),  # Nov 1 01:03 PDT
        utc(2026, 11, 1, 11, 3),  # Nov 1 03:03 PST (3 real hours later)
    ]


def test_spring_forward_odd_hours_unaffected():
    # Mar 14 2027: 02:00 PST -> 03:00 PDT. Odd hours 01 and 03 both exist,
    # one real hour apart.
    assert starts(HONEYING, utc(2027, 3, 14, 9, 0), 2) == [
        utc(2027, 3, 14, 9, 3),  # 01:03 PST
        utc(2027, 3, 14, 10, 3),  # 03:03 PDT
    ]


def test_spring_forward_skipped_time_does_not_happen():
    even = Event(key="even", name="Even", minute=30, emoji="⭐", first_hour=0)
    times = starts(even, utc(2027, 3, 14, 7, 0), 2)
    # 00:30 PST, then 02:30 doesn't exist, so 04:30 PDT.
    assert [t.astimezone(PACIFIC).hour for t in times] == [0, 4]


def test_current_occurrence_during_recruitment():
    occ = current_occurrence(HONEYING, utc(2026, 10, 6, 16, 20), PACIFIC)
    assert occ is not None
    assert occ.start == utc(2026, 10, 6, 16, 3)
    assert occ.end == utc(2026, 10, 6, 16, 33)


@pytest.mark.parametrize(
    "now",
    [utc(2026, 10, 6, 16, 2), utc(2026, 10, 6, 16, 33), utc(2026, 10, 6, 17, 0)],
)
def test_current_occurrence_outside_recruitment(now):
    assert current_occurrence(HONEYING, now, PACIFIC) is None


def test_current_occurrence_at_exact_start():
    occ = current_occurrence(HONEYING, utc(2026, 10, 6, 16, 3), PACIFIC)
    assert occ is not None and occ.start == utc(2026, 10, 6, 16, 3)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        next_occurrence(HONEYING, datetime(2026, 10, 6), PACIFIC)


@pytest.mark.parametrize(
    "kwargs",
    [{"interval_hours": 5}, {"minute": 60}, {"first_hour": 24}, {"duration_minutes": 0}],
)
def test_invalid_event_rejected(kwargs):
    with pytest.raises(ValueError):
        Event(key="bad", name="Bad", emoji="⭐", **{"minute": 0, **kwargs})


def test_hourly_event():
    hourly = Event(key="h", name="H", minute=15, emoji="⭐", interval_hours=1)
    times = starts(hourly, utc(2026, 10, 6), 3)
    assert all(b - a == timedelta(hours=1) for a, b in zip(times, times[1:], strict=False))
