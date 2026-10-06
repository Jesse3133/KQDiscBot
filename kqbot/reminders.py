"""Which reminders are due right now. Pure logic, no Discord."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from kqbot.events import Event
from kqbot.schedule import Occurrence, next_occurrence

REMINDER_LEAD = timedelta(minutes=3)
# Test reminders clean themselves up after this long.
TEST_LIFETIME = timedelta(minutes=5)


def due_reminders(
    events: tuple[Event, ...], now: datetime, tz: ZoneInfo, lead: timedelta = REMINDER_LEAD
) -> list[Occurrence]:
    """Occurrences whose reminder window is open: ``start - lead <= now < start``.

    Once an event has started its reminder is no longer due, so a bot that was
    offline doesn't post "starting soon" for something already running.
    """
    due = []
    for event in events:
        occ = next_occurrence(event, now, tz)
        if occ.start - lead <= now:
            due.append(occ)
    return due
