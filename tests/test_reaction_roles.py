import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from kqbot.cogs.reaction_roles import ReactionRoles
from kqbot.db import Database, GuildSettings
from kqbot.events import DEFAULT_EVENTS, find_event_by_emoji

GUILD_ID, MESSAGE_ID, BOT_ID, USER_ID, ROLE_ID = 1, 2, 3, 4, 5


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.save_guild(GuildSettings(GUILD_ID, 10, 20, MESSAGE_ID))
    db.set_event_role(GUILD_ID, "honeying", ROLE_ID)

    role = SimpleNamespace(id=ROLE_ID, name="Mean Giant Honeying")
    member = MagicMock(bot=False, add_roles=AsyncMock(), remove_roles=AsyncMock())
    guild = MagicMock(id=GUILD_ID)
    guild.get_role = lambda rid: role if rid == ROLE_ID else None
    guild.get_member = lambda uid: None
    guild.fetch_member = AsyncMock(return_value=member)

    bot = SimpleNamespace(
        db=db, events=DEFAULT_EVENTS, user=SimpleNamespace(id=BOT_ID), get_guild=lambda gid: guild
    )
    yield ReactionRoles(bot), member, role
    db.close()


def payload(emoji="🍯", user_id=USER_ID, message_id=MESSAGE_ID, member=None):
    return SimpleNamespace(
        guild_id=GUILD_ID, message_id=message_id, user_id=user_id, emoji=emoji, member=member
    )


def test_add_gives_role(setup):
    cog, member, role = setup
    asyncio.run(cog.on_raw_reaction_add(payload(member=member)))
    member.add_roles.assert_awaited_once()
    assert member.add_roles.await_args.args == (role,)


def test_remove_takes_role(setup):
    cog, member, role = setup
    asyncio.run(cog.on_raw_reaction_remove(payload()))
    member.remove_roles.assert_awaited_once()
    assert member.remove_roles.await_args.args == (role,)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"message_id": 999},  # some other message
        {"user_id": BOT_ID},  # the bot's own reactions
        {"emoji": "😀"},  # not an event emoji
        {"emoji": "🐉"},  # event without a stored role
    ],
)
def test_ignored(setup, kwargs):
    cog, member, _ = setup
    asyncio.run(cog.on_raw_reaction_add(payload(member=member, **kwargs)))
    member.add_roles.assert_not_awaited()


def test_ignores_other_bots(setup):
    cog, member, _ = setup
    member.bot = True
    asyncio.run(cog.on_raw_reaction_add(payload(member=member)))
    member.add_roles.assert_not_awaited()


def test_emoji_match_ignores_variation_selector():
    pirates = next(e for e in DEFAULT_EVENTS if e.key == "pirates")
    bare = pirates.emoji.replace("️", "")
    assert bare != pirates.emoji
    assert find_event_by_emoji(DEFAULT_EVENTS, bare) is pirates
