"""Kingdom Quest definitions.

Each event repeats every ``interval_hours`` hours at ``minute`` past the hour,
on local game-time hours that line up with ``first_hour``. With the defaults
(interval 2, first hour 1) that means the odd hours: 01, 03, 05, ... 23.
"""

import re
from dataclasses import dataclass

# Intervals must divide a day evenly so the pattern is identical every day.
VALID_INTERVALS = (1, 2, 3, 4, 6, 8, 12, 24)
# Discord allows at most 20 different reactions on one message (the role picker).
MAX_EVENTS = 20
MAX_NAME_LENGTH = 80

# Custom emoji markup, e.g. <:honey:1234567890> or <a:spin:1234567890> (animated).
CUSTOM_EMOJI = re.compile(r"<a?:(\w{2,32}):(\d{15,25})>")


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
        if not 1 <= self.duration_minutes <= 24 * 60:
            raise ValueError("duration must be between 1 and 1440 minutes")
        if not self.name.strip() or len(self.name) > MAX_NAME_LENGTH:
            raise ValueError(f"name must be 1 to {MAX_NAME_LENGTH} characters")
        if not is_emoji(self.emoji):
            raise ValueError("emoji must be a single emoji or a custom emoji like <:name:id>")

    def runs_at_hour(self, hour: int) -> bool:
        return (hour - self.first_hour) % self.interval_hours == 0


def custom_emoji_id(emoji: str) -> int | None:
    match = CUSTOM_EMOJI.fullmatch(emoji.strip())
    return int(match.group(2)) if match else None


def is_emoji(text: str) -> bool:
    """A custom emoji, or a short run of non-ASCII symbols (a Unicode emoji)."""
    text = text.strip()
    if custom_emoji_id(text) is not None:
        return True
    return 0 < len(text) <= 16 and all(not ch.isascii() or ch == "\u200d" for ch in text)


def normalize_emoji(emoji: str) -> str:
    """Comparable form of an emoji.

    Custom emojis compare by ID (their name can change). Unicode emojis drop
    variation selectors so e.g. "🏴‍☠️" matches with or without U+FE0F.
    """
    custom_id = custom_emoji_id(emoji)
    if custom_id is not None:
        return f"custom:{custom_id}"
    return emoji.strip().replace("\ufe0f", "")


def make_key(name: str, taken: set[str]) -> str:
    """Short unique ID for a new event, derived from its name."""
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "event"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}-{n}", n + 1
    return key


def find_event_by_emoji(events: tuple[Event, ...], emoji: str) -> Event | None:
    target = normalize_emoji(emoji)
    return next((e for e in events if normalize_emoji(e.emoji) == target), None)


# Seed data: written to the database on first start. After that the database
# is the source of truth, edited with the /event commands.
DEFAULT_EVENTS: tuple[Event, ...] = (
    Event(key="brigade", name="Midnight Brigade Veteran", minute=0, emoji="🌙"),
    Event(key="robo", name="The Millennium Robo Plot", minute=1, emoji="🤖"),
    Event(key="honeying", name="Mean Giant Honeying", minute=3, emoji="🍯"),
    Event(key="dragon", name="Mini Dragon HC", minute=9, emoji="🐉"),
    Event(key="pirates", name="Mara Pirates' Rage", minute=12, emoji="🏴‍☠️"),
)
