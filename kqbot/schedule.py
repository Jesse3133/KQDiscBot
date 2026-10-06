"""Pure schedule math: when does an event next start?

All inputs and outputs are timezone-aware datetimes. Event hours are defined
in the game's local time zone, so daylight saving is handled here:

* When clocks fall back, the repeated hour (e.g. 01:xx) counts only once,
  at its first occurrence.
* When clocks spring forward, a start time inside the skipped hour does not
  happen at all.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from kqbot.events import Event


@dataclass(frozen=True)
class Occurrence:
    event: Event
    start: datetime  # UTC

    @property
    def end(self) -> datetime:
        """When recruitment closes."""
        return self.start + timedelta(minutes=self.event.duration_minutes)

    def is_active(self, now: datetime) -> bool:
        return self.start <= now < self.end


def _exists(local: datetime) -> bool:
    """False for wall-clock times skipped by a spring-forward transition."""
    roundtrip = local.astimezone(UTC).astimezone(local.tzinfo)
    return roundtrip.replace(tzinfo=None) == local.replace(tzinfo=None)


def _starts_on(event: Event, day: date, tz: ZoneInfo) -> Iterator[datetime]:
    for hour in range(24):
        if not event.runs_at_hour(hour):
            continue
        # fold=0 picks the first of two repeated wall times on fall-back night.
        local = datetime.combine(day, time(hour, event.minute), tzinfo=tz)
        if _exists(local):
            yield local.astimezone(UTC)


def occurrences(event: Event, after: datetime, tz: ZoneInfo) -> Iterator[Occurrence]:
    """Yield the event's occurrences that start strictly after ``after``, in order."""
    if after.tzinfo is None:
        raise ValueError("'after' must be timezone-aware")
    day = after.astimezone(tz).date() - timedelta(days=1)
    while True:
        for start in _starts_on(event, day, tz):
            if start > after:
                yield Occurrence(event, start)
        day += timedelta(days=1)


def next_occurrence(event: Event, now: datetime, tz: ZoneInfo) -> Occurrence:
    return next(occurrences(event, now, tz))


def current_occurrence(event: Event, now: datetime, tz: ZoneInfo) -> Occurrence | None:
    """The occurrence whose recruitment window is open at ``now``, if any."""
    lookback = now - timedelta(minutes=event.duration_minutes)
    occ = next(occurrences(event, lookback - timedelta(microseconds=1), tz))
    return occ if occ.is_active(now) else None
