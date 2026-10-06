import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from kqbot.bot import EXTENSIONS, AllowlistTree, KQBot
from kqbot.config import Config, parse_guild_ids

ALLOWED, OTHER = 111111111111111111, 222222222222222222


def make_bot(tmp_path, allowed=frozenset({ALLOWED})):
    async def make():
        config = Config(
            "x",
            ZoneInfo("America/Los_Angeles"),
            None,
            str(tmp_path / "t.sqlite3"),
            allowed_guild_ids=allowed,
        )
        bot = KQBot(config)
        for ext in EXTENSIONS:
            await bot.load_extension(ext)
        bot.get_cog("Reminders").check.cancel()
        return bot

    return asyncio.run(make())


@pytest.mark.parametrize(
    ("raw", "ids"),
    [("", set()), ("123", {123}), ("123, 456", {123, 456}), (" 123 456,789 ", {123, 456, 789})],
)
def test_parse_guild_ids(raw, ids):
    assert parse_guild_ids(raw) == ids


def test_parse_guild_ids_rejects_junk():
    with pytest.raises(SystemExit):
        parse_guild_ids("my server")


def test_is_allowed(tmp_path):
    bot = make_bot(tmp_path)
    assert bot.is_allowed(ALLOWED) and not bot.is_allowed(OTHER)
    bot.db.close()


def test_empty_allowlist_allows_everything(tmp_path):
    bot = make_bot(tmp_path, allowed=frozenset())
    assert bot.is_allowed(OTHER)
    bot.db.close()


def test_bot_uses_allowlist_tree(tmp_path):
    bot = make_bot(tmp_path)
    assert isinstance(bot.tree, AllowlistTree)
    bot.db.close()


def interaction(guild_id):
    inter = MagicMock(guild_id=guild_id)
    inter.response.send_message = AsyncMock()
    return inter


def test_commands_refused_in_other_servers(tmp_path):
    bot = make_bot(tmp_path)
    inter = interaction(OTHER)
    assert asyncio.run(bot.tree.interaction_check(inter)) is False
    assert "isn't enabled" in inter.response.send_message.await_args.args[0]
    assert asyncio.run(bot.tree.interaction_check(interaction(ALLOWED))) is True
    assert asyncio.run(bot.tree.interaction_check(interaction(None))) is True  # DMs: /next
    bot.db.close()


def test_leaves_server_it_is_not_allowed_in(tmp_path):
    bot = make_bot(tmp_path)
    guild = MagicMock(id=OTHER, leave=AsyncMock())
    asyncio.run(bot.get_cog("SetupCommands").on_guild_join(guild))
    guild.leave.assert_awaited_once()
    assert bot.db.get_guild(OTHER) is None
    bot.db.close()


def test_sets_up_allowed_server_on_join(tmp_path):
    bot = make_bot(tmp_path)
    cog = bot.get_cog("SetupCommands")
    cog._setup_quietly = AsyncMock()
    guild = MagicMock(id=ALLOWED, leave=AsyncMock())
    asyncio.run(cog.on_guild_join(guild))
    guild.leave.assert_not_awaited()
    cog._setup_quietly.assert_awaited_once_with(guild)
    bot.db.close()


def test_no_reminders_for_other_servers(tmp_path):
    from datetime import UTC, datetime

    from kqbot.db import GuildSettings

    bot = make_bot(tmp_path)
    bot.db.save_guild(GuildSettings(OTHER, alerts_channel_id=1))
    reminders = bot.get_cog("Reminders")
    reminders.post = AsyncMock()
    # 15:57 UTC on Oct 6 2026 is 3 minutes before Brigade.
    asyncio.run(reminders.tick(datetime(2026, 10, 6, 15, 57, tzinfo=UTC)))
    reminders.post.assert_not_awaited()

    # Control: the allowed server does get it at the same moment.
    bot.db.save_guild(GuildSettings(ALLOWED, alerts_channel_id=1))
    asyncio.run(reminders.tick(datetime(2026, 10, 6, 15, 57, tzinfo=UTC)))
    assert reminders.post.await_count == 1
    assert reminders.post.await_args.args[0].guild_id == ALLOWED
    bot.db.close()


def test_reactions_ignored_in_other_servers(tmp_path):
    bot = make_bot(tmp_path)
    member = MagicMock(add_roles=AsyncMock())
    bot._connection.user = SimpleNamespace(id=1)
    real_get_guild = bot.db.get_guild
    bot.db.get_guild = MagicMock(return_value=None)
    cog = bot.get_cog("ReactionRoles")

    payload = SimpleNamespace(guild_id=OTHER, user_id=2, message_id=3, emoji="🍯", member=member)
    asyncio.run(cog.on_raw_reaction_add(payload))
    bot.db.get_guild.assert_not_called()  # stopped before even looking it up

    payload.guild_id = ALLOWED  # control: an allowed server is looked up
    asyncio.run(cog.on_raw_reaction_add(payload))
    bot.db.get_guild.assert_called_once_with(ALLOWED)
    member.add_roles.assert_not_awaited()
    bot.db.get_guild = real_get_guild
    bot.db.close()
