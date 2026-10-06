"""Runs the admin slash commands against the real bot with faked Discord objects."""

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import discord
import pytest

from kqbot.bot import EXTENSIONS, KQBot
from kqbot.config import Config
from tests.fakes import FakeGuild

INTERVAL_2 = SimpleNamespace(value=2)


@pytest.fixture
def env(tmp_path, monkeypatch):
    async def make():
        config = Config("x", ZoneInfo("America/Los_Angeles"), None, str(tmp_path / "t.sqlite3"))
        bot = KQBot(config)
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        bot.get_cog("Reminders").check.cancel()
        return bot

    bot = asyncio.run(make())
    guild = FakeGuild()
    bot.get_guild = lambda gid: guild if gid == guild.id else None
    bot.get_emoji = lambda eid: None
    bot.fetch_application_emojis = AsyncMock(return_value=[SimpleNamespace(id=123456789012345678)])
    asyncio.run(bot.get_cog("SetupCommands").run_setup(guild))
    yield SimpleNamespace(bot=bot, guild=guild, cog=bot.get_cog("AdminCommands"))
    bot.db.close()


def interaction(guild):
    inter = MagicMock(guild=guild)
    inter.user.id = 42
    inter.response.send_message = AsyncMock()
    inter.response.defer = AsyncMock()
    inter.followup.send = AsyncMock()
    inter.edit_original_response = AsyncMock()
    return inter


def reply(inter) -> str:
    """The text the user ends up seeing: an edited response wins over the first one."""
    for mock in (inter.edit_original_response, inter.followup.send, inter.response.send_message):
        if mock.await_count:
            call = mock.await_args
            return call.args[0] if call.args else call.kwargs["content"]
    raise AssertionError("no reply sent")


def call(command, env, inter, *args, **kwargs):
    asyncio.run(command.callback(env.cog, inter, *args, **kwargs))
    return reply(inter)


def confirm_view_class(env):
    # discord.py loads extensions as fresh module objects, so patch the one in use.
    return sys.modules[type(env.cog).__module__].ConfirmView


def picker(env):
    settings = env.bot.db.get_guild(env.guild.id)
    channel = env.guild.get_channel(settings.roles_channel_id)
    return channel.messages[settings.roles_message_id]


def test_add_event_creates_role_and_reaction(env):
    inter = interaction(env.guild)
    text = call(env.cog.event_add, env, inter, "World Boss", 30, "👹", INTERVAL_2, 0, 15)
    assert "Added 👹 **World Boss**" in text
    assert env.bot.events[-1].key == "world-boss"
    assert any(r.name == "World Boss" for r in env.guild.roles)
    assert "👹" in [r.emoji for r in picker(env).reactions]


def test_add_rejects_duplicates_and_bad_emoji(env):
    assert "already exists" in call(
        env.cog.event_add, env, interaction(env.guild), "mean giant honeying", 5, "⭐"
    )
    assert "already uses that emoji" in call(
        env.cog.event_add, env, interaction(env.guild), "New", 5, "🍯"
    )
    assert "Can't add that" in call(env.cog.event_add, env, interaction(env.guild), "New", 5, "x")
    assert "can't use that custom emoji" in call(
        env.cog.event_add, env, interaction(env.guild), "New", 5, "<:nope:999999999999999999>"
    )
    assert len(env.bot.events) == 5


def test_add_with_application_emoji(env):
    text = call(
        env.cog.event_add, env, interaction(env.guild), "Custom", 5, "<:honey:123456789012345678>"
    )
    assert text.startswith("Added")


def test_edit_renames_role_and_changes_minute(env):
    role_id = env.bot.db.get_event_roles(env.guild.id)["honeying"]
    text = call(env.cog.event_edit, env, interaction(env.guild), "honeying", "Honey Time", 4)
    assert "Updated" in text and "Honey Time" in text and ":04" in text
    assert env.guild.get_role(role_id).name == "Honey Time"
    assert "Honey Time" in picker(env).content


def test_edit_needs_a_change(env):
    assert "Nothing to change" in call(env.cog.event_edit, env, interaction(env.guild), "honeying")


def test_remove_after_confirm(env, monkeypatch):
    async def confirmed_wait(self):
        self.confirmed = True
        return False

    monkeypatch.setattr(confirm_view_class(env), "wait", confirmed_wait)
    role = env.guild.get_role(env.bot.db.get_event_roles(env.guild.id)["honeying"])
    role.delete = AsyncMock(side_effect=lambda **kw: env.guild.roles.remove(role))

    text = call(env.cog.event_remove, env, interaction(env.guild), "honeying")
    assert text == "Removed **Mean Giant Honeying**."
    assert "honeying" not in [e.key for e in env.bot.events]
    assert role not in env.guild.roles
    assert "🍯" not in [r.emoji for r in picker(env).reactions]


def test_remove_cancelled(env, monkeypatch):
    async def cancelled_wait(self):
        return False  # finished without confirming (Cancel button)

    monkeypatch.setattr(confirm_view_class(env), "wait", cancelled_wait)
    call(env.cog.event_remove, env, interaction(env.guild), "honeying")
    assert "honeying" in [e.key for e in env.bot.events]


def test_shift_and_undo(env):
    now = datetime.now(UTC)
    honeying = next(e for e in env.bot.events if e.key == "honeying")
    normal = env.bot.schedule.next(honeying, now)
    text = call(env.cog.shift, env, interaction(env.guild), "honeying", 20)
    assert "now starts" in text
    moved = env.bot.schedule.next(honeying, now)
    assert moved.start == normal.start + timedelta(minutes=20)

    text = call(env.cog.shift, env, interaction(env.guild), "honeying", 0)
    assert "back to normal" in text
    assert env.bot.schedule.next(honeying, now).start == normal.start


def test_shift_all(env):
    text = call(env.cog.shift, env, interaction(env.guild), "*", 15)
    assert text.count("now starts") == 5


def test_config_timezone(env):
    text = call(env.cog.config_timezone, env, interaction(env.guild), "UTC")
    assert "now `UTC`" in text
    assert env.bot.game_tz.key == "UTC"
    assert env.bot.db.get_setting("timezone") == "UTC"
    assert "isn't a time zone" in call(
        env.cog.config_timezone, env, interaction(env.guild), "Mars/Base"
    )


def test_timezone_survives_restart(env, tmp_path):
    call(env.cog.config_timezone, env, interaction(env.guild), "UTC")
    config = Config("x", ZoneInfo("America/Los_Angeles"), None, str(tmp_path / "t.sqlite3"))
    assert KQBot(config).game_tz.key == "UTC"


def test_config_alerts_channel(env):
    channel = MagicMock(spec=discord.TextChannel, id=777, mention="#new")
    channel.permissions_for.return_value = discord.Permissions(
        view_channel=True, send_messages=True, add_reactions=True, read_message_history=True
    )
    text = call(env.cog.config_alerts, env, interaction(env.guild), channel)
    assert "#new" in text
    assert env.bot.db.get_guild(env.guild.id).alerts_channel_id == 777

    channel.permissions_for.return_value = discord.Permissions.none()
    assert "can't use that channel" in call(
        env.cog.config_alerts, env, interaction(env.guild), channel
    )


def test_config_show(env):
    text = call(env.cog.config_show, env, interaction(env.guild))
    assert "America/Los_Angeles" in text and "3 minutes" in text and "Events:** 5" in text


def test_event_list(env):
    text = call(env.cog.event_list, env, interaction(env.guild))
    assert text.count("every 2 hours") == 5


def test_add_with_levels_goes_in_level_order(env):
    text = call(
        env.cog.event_add, env, interaction(env.guild), "Starter", 7, "🌱", None, 1, 30, 5, 15
    )
    assert "(Lv 5-15)" in text
    assert env.bot.events[0].key == "starter"
    first_line = picker(env).content.splitlines()[3]
    assert first_line.startswith("🌱 Starter (Lv 5-15)")


def test_edit_levels_reorders_and_clears(env):
    def edit(**kwargs):
        return call(env.cog.event_edit, env, interaction(env.guild), "pirates", **kwargs)

    assert "(Lv 70-80)" in edit(min_level=70, max_level=80)
    assert [e.key for e in env.bot.events][-1] == "pirates"
    assert "Updated" in edit(min_level=0, max_level=0)
    pirates = next(e for e in env.bot.events if e.key == "pirates")
    assert pirates.levels == ""
    assert "set both" in edit(min_level=20)
