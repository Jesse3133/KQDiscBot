"""Kingdom Quest definitions.

Each event repeats every ``interval_hours`` hours at ``minute`` past the hour,
on local game-time hours that line up with ``first_hour``. With the defaults
(interval 2, first hour 1) that means the odd hours: 01, 03, 05, ... 23.
"""

from dataclasses import dataclass

# Intervals must divide a day evenly so the pattern is identical every day.
VALID_INTERVALS = (1, 2, 3, 4, 6, 8, 12, 24)


@dataclass(frozen=True)
class Event:
    key: str
    name: str
    minute: int
    emoji: str
    interval_hours: int = 2
    first_hour: int = 1
    duration_minutes: int = 30

    def __post_init__(self) -> None:
        if self.interval_hours not in VALID_INTERVALS:
            raise ValueError(f"interval_hours must be one of {VALID_INTERVALS}")
        if not 0 <= self.minute <= 59:
            raise ValueError("minute must be between 0 and 59")
        if not 0 <= self.first_hour <= 23:
            raise ValueError("first_hour must be between 0 and 23")
        if self.duration_minutes <= 0:
            raise ValueError("duration_minutes must be positive")

    def runs_at_hour(self, hour: int) -> bool:
        return (hour - self.first_hour) % self.interval_hours == 0


# Seed data. Later phases move these into the database so admins can edit
# them with slash commands; until then this list is the source of truth.
DEFAULT_EVENTS: tuple[Event, ...] = (
    Event(key="brigade", name="Midnight Brigade Veteran", minute=0, emoji="🌙"),
    Event(key="robo", name="The Millennium Robo Plot", minute=1, emoji="🤖"),
    Event(key="honeying", name="Mean Giant Honeying", minute=3, emoji="🍯"),
    Event(key="dragon", name="Mini Dragon HC", minute=9, emoji="🐉"),
    Event(key="pirates", name="Mara Pirates' Rage", minute=12, emoji="🏴‍☠️"),
)
