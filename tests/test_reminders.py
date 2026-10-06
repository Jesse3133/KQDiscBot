import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import discord
import pytest

from kqbot.cogs.reminders import Reminders, find_problems
from kqbot.db import Database, GuildSettings, PendingDelete
from kqbot.events import DEFAULT_EVENTS
from kqbot.formatting import reminder_message, ts
from kqbot.reminders import due_reminders
from kqbot.schedule import Occurrence, Schedule
from tests.fakes import FakeChannel, FakeGuild, FakeRole

PACIFIC = ZoneInfo("America/Los_Angeles")
EVENTS = {e.key: e for e in DEFAULT_EVENTS}


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def due_keys(now):
    return [o.event.key for o in due_reminders(DEFAULT_EVENTS, now, Schedule(PACIFIC))]


# Pure timing ---------------------------------------------------------------


def test_due_exactly_three_minutes_before():
    # Brigade starts 16:00 UTC on Oct 6 (09:00 PDT).
    assert due_keys(utc(2026, 10, 6, 15, 56, 59)) == []
    assert due_keys(utc(2026, 10, 6, 15, 57)) == ["brigade"]
    assert due_keys(utc(2026, 10, 6, 15, 58)) == ["brigade", "robo"]


def test_not_due_once_started():
    # At 16:00 Brigade has started; Robo (16:01) and Honeying (16:03) are due.
    assert due_keys(utc(2026, 10, 6, 16, 0)) == ["robo", "honeying"]


def test_quiet_between_events():
    assert due_keys(utc(2026, 10, 6, 17, 0)) == []


# Message text ----------------------------------------------------------------


def test_reminder_message():
    occ = Occurrence(EVENTS["honeying"], utc(2026, 10, 6, 16, 3))
    text = reminder_message(occ, 42)
    assert text.startswith("<@&42> 🍯 **Mean Giant Honeying** is starting soon!")
    assert ts(occ.start, "t") in text and ts(occ.start, "R") in text
    assert f"Recruitment closes {ts(occ.end, 't')}" in text
    assert "Test" not in text


def test_reminder_message_without_role_and_test():
    occ = Occurrence(EVENTS["honeying"], utc(2026, 10, 6, 16, 3))
    text = reminder_message(occ, None, test=True)
    assert "<@&" not in text
    assert text.startswith("🧪 **Test reminder**")


# The loop ---------------------------------------------------------------------


@pytest.fixture
def world(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.seed_events(DEFAULT_EVENTS)
    alerts = FakeChannel("kq-alerts")
    guild = FakeGuild(text_channels=[alerts])
    honeying_role = FakeRole("Mean Giant Honeying", mentionable=True)
    guild.roles.append(honeying_role)
    db.save_guild(GuildSettings(guild.id, alerts_channel_id=alerts.id))
    db.set_event_role(guild.id, "honeying", honeying_role.id)

    deleted = []

    class Partial:
        def __init__(self, channel_id):
            self.channel_id = channel_id

        def get_partial_message(self, message_id):
            async def delete():
                deleted.append(message_id)
                alerts.messages.pop(message_id, None)

            return SimpleNamespace(delete=delete)

    bot = SimpleNamespace(
        db=db,
        events=DEFAULT_EVENTS,
        schedule=Schedule(PACIFIC),
        get_guild=lambda gid: guild if gid == guild.id else None,
        get_partial_messageable=Partial,
    )
    yield SimpleNamespace(
        cog=Reminders(bot), db=db, guild=guild, alerts=alerts, role=honeying_role, deleted=deleted
    )
    db.close()


def tick(world, now):
    asyncio.run(world.cog.tick(now))


def test_posts_reminder_with_ping_and_reactions(world):
    tick(world, utc(2026, 10, 6, 16, 0, 30))  # Honeying (16:03) is due
    (message,) = [m for m in world.alerts.messages.values() if "Honeying" in m.content]
    assert message.content.startswith(f"<@&{world.role.id}>")
    assert [r.emoji for r in message.reactions] == ["✅", "❌"]
    assert message.allowed_mentions.roles is True
    assert message.allowed_mentions.everyone is False


def test_posts_each_reminder_once(world):
    tick(world, utc(2026, 10, 6, 16, 0, 30))
    count = len(world.alerts.messages)
    tick(world, utc(2026, 10, 6, 16, 0, 40))
    tick(world, utc(2026, 10, 6, 16, 2, 50))
    assert len(world.alerts.messages) == count


def test_separate_message_per_event(world):
    tick(world, utc(2026, 10, 6, 15, 57))  # Brigade
    tick(world, utc(2026, 10, 6, 15, 58))  # Robo
    tick(world, utc(2026, 10, 6, 16, 0, 30))  # Honeying
    names = [m.content.split("**")[1] for m in world.alerts.messages.values()]
    assert names == [
        "Midnight Brigade Veteran",
        "The Millennium Robo Plot",
        "Mean Giant Honeying",
    ]


def test_missing_role_posts_without_ping(world):
    tick(world, utc(2026, 10, 6, 15, 57))  # Brigade has no role in this fixture
    (message,) = world.alerts.messages.values()
    assert "<@&" not in message.content


def test_deleted_when_recruitment_closes(world):
    tick(world, utc(2026, 10, 6, 16, 0, 30))
    honeying = next(m for m in world.alerts.messages.values() if "Honeying" in m.content)
    tick(world, utc(2026, 10, 6, 16, 32, 59))
    assert honeying.id not in world.deleted
    tick(world, utc(2026, 10, 6, 16, 33))
    assert honeying.id in world.deleted
    assert world.db.due_deletes(int(utc(2027, 1, 1).timestamp())) == []


def test_restart_skips_started_events(world):
    tick(world, utc(2026, 10, 6, 16, 4))  # Honeying started at 16:03
    assert world.alerts.messages == {}


def test_missing_channel_logs_and_does_not_retry(world, caplog):
    world.guild.text_channels.clear()
    tick(world, utc(2026, 10, 6, 15, 57))
    tick(world, utc(2026, 10, 6, 15, 57, 10))
    assert caplog.text.count("Alerts channel missing") == 1


def test_failed_delete_is_retried(world):
    world.db.schedule_delete(PendingDelete(1, 2, 0))

    def broken(channel_id):
        async def delete():
            raise discord.HTTPException(MagicMock(status=500, reason="err"), "boom")

        return SimpleNamespace(get_partial_message=lambda mid: SimpleNamespace(delete=delete))

    world.cog.bot.get_partial_messageable = broken
    tick(world, utc(2026, 10, 6, 17, 0))
    assert world.db.due_deletes(10**12) == [PendingDelete(1, 2, 0)]


def test_already_deleted_message_is_forgotten(world):
    world.db.schedule_delete(PendingDelete(1, 2, 0))

    def gone(channel_id):
        async def delete():
            raise discord.NotFound(MagicMock(status=404, reason="nf"), "Unknown Message")

        return SimpleNamespace(get_partial_message=lambda mid: SimpleNamespace(delete=delete))

    world.cog.bot.get_partial_messageable = gone
    tick(world, utc(2026, 10, 6, 17, 0))
    assert world.db.due_deletes(10**12) == []


# Troubleshooting checks ------------------------------------------------------------


def make_channel(**perms):
    base = {
        "view_channel": True,
        "send_messages": True,
        "add_reactions": True,
        "read_message_history": True,
    }
    permissions = discord.Permissions.none()
    permissions.update(**{**base, **perms})
    return SimpleNamespace(
        guild=SimpleNamespace(me=object()),
        mention="#kq-alerts",
        permissions_for=lambda member: permissions,
    )


def test_find_problems_all_good():
    role = SimpleNamespace(mentionable=True, mention="@H")
    assert find_problems(make_channel(), [EVENTS["honeying"]], {"honeying": role}) == []


def test_find_problems_reports_each_issue():
    role = SimpleNamespace(mentionable=False, mention="@H")
    problems = find_problems(
        make_channel(send_messages=False),
        [EVENTS["honeying"], EVENTS["dragon"]],
        {"honeying": role, "dragon": None},
    )
    assert len(problems) == 3
    assert "Send Messages" in problems[0]
    assert "isn't mentionable" in problems[1]
    assert "Mini Dragon HC" in problems[2] and "/setup" in problems[2]


def test_mention_everyone_permission_overrides_unmentionable_role():
    role = SimpleNamespace(mentionable=False, mention="@H")
    channel = make_channel(mention_everyone=True)
    assert find_problems(channel, [EVENTS["honeying"]], {"honeying": role}) == []


# Database -------------------------------------------------------------------------


def test_sent_reminders_and_prune(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    assert not db.reminder_sent(1, "honeying", 100)
    db.mark_reminder_sent(1, "honeying", 100)
    db.mark_reminder_sent(1, "honeying", 100)
    assert db.reminder_sent(1, "honeying", 100)
    assert not db.reminder_sent(2, "honeying", 100)
    db.prune_sent_reminders(101)
    assert not db.reminder_sent(1, "honeying", 100)
    db.close()


def test_due_deletes_ordering(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    db.schedule_delete(PendingDelete(1, 9, 200))
    db.schedule_delete(PendingDelete(2, 9, 100))
    db.schedule_delete(PendingDelete(3, 9, 300))
    assert [d.message_id for d in db.due_deletes(250)] == [2, 1]
    db.remove_pending_delete(2)
    assert [d.message_id for d in db.due_deletes(250)] == [1]
    db.close()


def test_one_day_of_reminders_is_twelve_per_event():
    now = utc(2026, 10, 6, 7, 0)
    posted = set()
    for minute in range(24 * 60):
        moment = now + timedelta(minutes=minute)
        for occ in due_reminders(DEFAULT_EVENTS, moment, Schedule(PACIFIC)):
            posted.add((occ.event.key, occ.start))
    assert len(posted) == 12 * len(DEFAULT_EVENTS)
