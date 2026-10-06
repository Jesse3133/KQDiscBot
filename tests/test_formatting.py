from datetime import UTC, datetime

from kqbot.events import DEFAULT_EVENTS, Event
from kqbot.formatting import next_line, roles_message, ts
from kqbot.schedule import Occurrence

HONEYING = next(e for e in DEFAULT_EVENTS if e.key == "honeying")
START = datetime(2026, 10, 6, 16, 3, tzinfo=UTC)


def test_ts():
    assert ts(START, "R") == f"<t:{int(START.timestamp())}:R>"


def test_upcoming_line():
    line = next_line(Occurrence(HONEYING, START), None)
    assert "**Mean Giant Honeying**" in line
    assert ts(START, "t") in line and ts(START, "R") in line
    assert "closes " + ts(Occurrence(HONEYING, START).end, "t") in line


def test_active_line():
    prev = Occurrence(HONEYING, START)
    nxt = Occurrence(HONEYING, START.replace(hour=18))
    line = next_line(nxt, prev)
    assert "recruiting now" in line
    assert ts(prev.end, "R") in line


def test_roles_message_lists_every_event():
    text = roles_message(DEFAULT_EVENTS, {"honeying": 42})
    assert "🍯 Mean Giant Honeying (Lv 40-50) → <@&42>" in text
    assert text.endswith("🐉 Mini Dragon HC (Lv 46-60)")
    assert text.count("\n") >= len(DEFAULT_EVENTS)


def test_roles_message_without_levels():
    plain = (Event("a", "Plain", 0, "⭐"),)
    assert roles_message(plain, {}).endswith("⭐ Plain")
