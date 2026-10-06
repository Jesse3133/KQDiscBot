"""Pure schedule math: when does an event next start?

All inputs and outputs are timezone-aware datetimes. Event hours are defined
in the game's local time zone, so daylight saving is handled here:

* When clocks fall back, the repeated hour (e.g. 01:xx) counts only once,
  at its first occurrence.
* When clocks spring forward, a start time inside the skipped hour does not
  happen at all.

Single occurrences can be moved with a shift (see ``Schedule.shifts``), e.g.
when maintenance delays an event.
"""

import heapq
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from kqbot.events import Event

# Largest allowed one-off shift, in minutes, either direction.
MAX_SHIFT_MINUTES = 180


@dataclass(frozen=True)
class Occurrence:
    event: Event
    start: datetime  # UTC
    normal_start: datetime | None = None  # set when this occurrence was shifted

    @property
    def end(self) -> datetime:
        """When recruitment closes."""
        return self.start + timedelta(minutes=self.event.duration_minutes)

    @property
    def base_start(self) -> datetime:
        """The regular schedule's start time, before any shift."""
        return self.normal_start or self.start

    @property
    def shifted(self) -> bool:
        return self.normal_start is not None and self.normal_start != self.start

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


@dataclass(frozen=True)
class Schedule:
    tz: ZoneInfo
    # event key -> {regular start (unix seconds) -> minutes moved}
    shifts: Mapping[str, Mapping[int, int]] = field(default_factory=dict)

    def occurrences(self, event: Event, after: datetime) -> Iterator[Occurrence]:
        """Yield the event's occurrences that start strictly after ``after``, in order."""
        if after.tzinfo is None:
            raise ValueError("'after' must be timezone-aware")
        shifts = self.shifts.get(event.key, {})
        slack = timedelta(minutes=max((abs(m) for m in shifts.values()), default=0))
        # A shift can move an occurrence past later ones, so hold occurrences
        # back until no later regular start could still land before them.
        pending: list[tuple[datetime, datetime, Occurrence]] = []
        day = after.astimezone(self.tz).date() - timedelta(days=1)
        while True:
            for base in _starts_on(event, day, self.tz):
                moved = shifts.get(int(base.timestamp()), 0)
                start = base + timedelta(minutes=moved)
                occ = Occurrence(event, start, base if moved else None)
                heapq.heappush(pending, (start, base, occ))
                while pending and pending[0][0] <= base - slack:
                    start, _, ready = heapq.heappop(pending)
                    if start > after:
                        yield ready
            day += timedelta(days=1)

    def next(self, event: Event, now: datetime) -> Occurrence:
        return next(self.occurrences(event, now))

    def current(self, event: Event, now: datetime) -> Occurrence | None:
        """The occurrence whose recruitment window is open at ``now``, if any."""
        lookback = now - timedelta(minutes=event.duration_minutes, microseconds=1)
        for occ in self.occurrences(event, lookback):
            if occ.start > now:
                return None
            if occ.is_active(now):
                return occ
        return None  # pragma: no cover (occurrences never ends)


# Shorthands for the common unshifted case.


def occurrences(event: Event, after: datetime, tz: ZoneInfo) -> Iterator[Occurrence]:
    return Schedule(tz).occurrences(event, after)


def next_occurrence(event: Event, now: datetime, tz: ZoneInfo) -> Occurrence:
    return Schedule(tz).next(event, now)


def current_occurrence(event: Event, now: datetime, tz: ZoneInfo) -> Occurrence | None:
    return Schedule(tz).current(event, now)
