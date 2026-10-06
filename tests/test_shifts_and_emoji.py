from datetime import UTC, datetime, timedelta
from itertools import islice
from zoneinfo import ZoneInfo

import pytest

from kqbot.db import Database
from kqbot.events import (
    DEFAULT_EVENTS,
    Event,
    custom_emoji_id,
    find_event_by_emoji,
    is_emoji,
    make_key,
    normalize_emoji,
)
from kqbot.formatting import describe_timing, reminder_message, ts
from kqbot.reminders import due_reminders
from kqbot.schedule import Schedule

PACIFIC = ZoneInfo("America/Los_Angeles")
HONEYING = next(e for e in DEFAULT_EVENTS if e.key == "honeying")
BASE = datetime(2026, 10, 6, 16, 3, tzinfo=UTC)  # a regular Honeying start


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def shifted(minutes: int) -> Schedule:
    return Schedule(PACIFIC, {"honeying": {int(BASE.timestamp()): minutes}})


# Shifts -------------------------------------------------------------------


def test_shift_later():
    occ = shifted(30).next(HONEYING, utc(2026, 10, 6, 15, 50))
    assert occ.start == BASE + timedelta(minutes=30)
    assert occ.normal_start == BASE and occ.shifted
    # The occurrence after it is back on the normal schedule.
    following = shifted(30).next(HONEYING, occ.start)
    assert following.start == BASE + timedelta(hours=2) and not following.shifted


def test_shift_only_affects_its_own_event():
    dragon = next(e for e in DEFAULT_EVENTS if e.key == "dragon")
    assert not shifted(30).next(dragon, utc(2026, 10, 6, 15, 50)).shifted


def test_shift_earlier_into_the_past_is_skipped():
    # Moved 15 min earlier to 15:48, which is before "now".
    occ = shifted(-15).next(HONEYING, utc(2026, 10, 6, 15, 50))
    assert occ.start == BASE + timedelta(hours=2)


def test_shift_past_the_next_regular_start_keeps_order():
    starts = [o.start for o in islice(shifted(150).occurrences(HONEYING, BASE - timedelta(1)), 30)]
    assert starts == sorted(starts)
    assert BASE + timedelta(minutes=150) in starts
    assert BASE not in starts


def test_current_during_shifted_recruitment():
    occ = shifted(30).current(HONEYING, utc(2026, 10, 6, 16, 40))
    assert occ is not None and occ.start == BASE + timedelta(minutes=30)
    # The normal window (16:03-16:33) is not active because it moved.
    assert shifted(30).current(HONEYING, utc(2026, 10, 6, 16, 10)) is None


def test_reminder_follows_shift():
    events = (HONEYING,)
    assert due_reminders(events, utc(2026, 10, 6, 16, 1), shifted(30)) == []
    (occ,) = due_reminders(events, utc(2026, 10, 6, 16, 31), shifted(30))
    assert occ.start == BASE + timedelta(minutes=30)
    assert f"(moved from {ts(BASE, 't')})" in reminder_message(occ, None)


# Emojis -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text", ["🍯", "🏴‍☠️", "🏴‍☠", "<:honey:123456789012345678>", "<a:spin:123456789012345678>"]
)
def test_is_emoji(text):
    assert is_emoji(text)


@pytest.mark.parametrize("text", ["", "x", "honey", ":honey:", "🍯 honey", "<:honey:12>"])
def test_not_emoji(text):
    assert not is_emoji(text)


def test_custom_emoji_compares_by_id():
    assert custom_emoji_id("<:honey:123456789012345678>") == 123456789012345678
    assert normalize_emoji("<:honey:123456789012345678>") == normalize_emoji(
        "<:renamed:123456789012345678>"
    )
    custom = Event(key="c", name="Custom", minute=5, emoji="<:honey:123456789012345678>")
    assert find_event_by_emoji((custom,), "<:honey:123456789012345678>") is custom


def test_make_key():
    assert make_key("Mean Giant Honeying", set()) == "mean-giant-honeying"
    assert make_key("Mara Pirates' Rage", set()) == "mara-pirates-rage"
    assert make_key("Boss!", {"boss", "boss-2"}) == "boss-3"
    assert make_key("!!!", set()) == "event"


@pytest.mark.parametrize(
    "kwargs", [{"name": ""}, {"name": "x" * 81}, {"emoji": "x"}, {"duration_minutes": 2000}]
)
def test_event_validation(kwargs):
    with pytest.raises(ValueError):
        Event(**{"key": "k", "name": "Name", "minute": 0, "emoji": "⭐", **kwargs})


# Timing description ---------------------------------------------------------------


def test_describe_timing():
    assert describe_timing(HONEYING) == "every 2 hours at :03 (01:03, 03:03, 05:03, …)"
    assert describe_timing(Event("a", "A", 15, "⭐", interval_hours=1)) == "every hour at :15"
    assert describe_timing(Event("a", "A", 0, "⭐", interval_hours=24, first_hour=20)) == (
        "daily at 20:00"
    )
    assert describe_timing(Event("a", "A", 0, "⭐", first_hour=4)).startswith(
        "every 2 hours at :00 (00:00, 02:00"
    )


# Database ----------------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "t.sqlite3")
    database.seed_events(DEFAULT_EVENTS)
    yield database
    database.close()


def test_add_update_delete_event(db):
    new = Event("boss", "World Boss", 30, "👹")
    db.add_event(new)
    assert db.load_events()[-1] == new

    db.update_event(Event("boss", "Big Boss", 45, "🐲", 4, 0, 15))
    assert db.load_events()[-1] == Event("boss", "Big Boss", 45, "🐲", 4, 0, 15)

    db.set_event_role(1, "boss", 99)
    db.set_shift("boss", 100, 10)
    db.delete_event("boss")
    assert db.load_events() == DEFAULT_EVENTS
    assert "boss" not in db.get_event_roles(1)
    assert "boss" not in db.load_shifts()


def test_settings(db):
    assert db.get_setting("timezone") is None
    db.set_setting("timezone", "UTC")
    db.set_setting("timezone", "America/New_York")
    assert db.get_setting("timezone") == "America/New_York"


def test_shifts(db):
    db.set_shift("honeying", 100, 15)
    db.set_shift("honeying", 200, -10)
    db.set_shift("dragon", 100, 5)
    assert db.load_shifts() == {"honeying": {100: 15, 200: -10}, "dragon": {100: 5}}
    db.set_shift("honeying", 100, 0)  # back to normal
    db.prune_shifts(150)
    assert db.load_shifts() == {"honeying": {200: -10}}
