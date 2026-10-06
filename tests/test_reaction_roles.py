import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from kqbot.cogs.reaction_roles import ReactionRoles
from kqbot.db import Database, GuildSettings
from kqbot.events import DEFAULT_EVENTS, find_event_by_emoji
from tests.fakes import FakeRole

GUILD_ID, MESSAGE_ID, BOT_ID, USER_ID, ROLE_ID = 1, 2, 3, 4, 5


@pytest.fixture
def setup(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.save_guild(GuildSettings(GUILD_ID, 10, 20, MESSAGE_ID))
    db.set_event_role(GUILD_ID, "honeying", ROLE_ID)

    role = FakeRole("Mean Giant Honeying", id=ROLE_ID)
    member = MagicMock(bot=False, add_roles=AsyncMock(), remove_roles=AsyncMock())
    guild = MagicMock(id=GUILD_ID)
    guild.get_role = lambda rid: role if rid == ROLE_ID else None
    guild.get_member = lambda uid: None
    guild.fetch_member = AsyncMock(return_value=member)

    bot = SimpleNamespace(
        is_allowed=lambda guild_id: True,
        db=db,
        events=DEFAULT_EVENTS,
        user=SimpleNamespace(id=BOT_ID),
        get_guild=lambda gid: guild,
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


def test_sync_gives_roles_for_offline_reactions(tmp_path):
    db = Database(tmp_path / "sync.sqlite3")
    db.save_guild(GuildSettings(GUILD_ID, 10, 20, MESSAGE_ID))
    db.set_event_role(GUILD_ID, "honeying", ROLE_ID)
    role = FakeRole("Mean Giant Honeying", id=ROLE_ID)

    has_role = MagicMock(bot=False, roles=[role], add_roles=AsyncMock())
    needs_role = MagicMock(bot=False, roles=[], add_roles=AsyncMock())
    members = {1: has_role, 2: needs_role}

    async def users():
        for uid, is_bot in ((1, False), (2, False), (BOT_ID, True)):
            yield SimpleNamespace(id=uid, bot=is_bot)

    reactions = [
        SimpleNamespace(emoji="🍯", users=users),
        SimpleNamespace(emoji="😀", users=users),  # not an event
    ]
    message = SimpleNamespace(reactions=reactions)
    channel = SimpleNamespace(fetch_message=AsyncMock(return_value=message))
    guild = MagicMock(id=GUILD_ID)
    guild.name = "Test"
    guild.get_channel = lambda cid: channel if cid == 20 else None
    guild.get_role = lambda rid: role if rid == ROLE_ID else None
    guild.get_member = lambda uid: members.get(uid)

    bot = SimpleNamespace(
        is_allowed=lambda guild_id: True,
        db=db,
        events=DEFAULT_EVENTS,
        user=SimpleNamespace(id=BOT_ID),
    )
    given = asyncio.run(ReactionRoles(bot).sync_guild(guild))
    assert given == 1
    needs_role.add_roles.assert_awaited_once()
    has_role.add_roles.assert_not_awaited()
    db.close()


@pytest.mark.parametrize(
    "change",
    [
        {"permissions": discord.Permissions(administrator=True)},
        {"permissions": discord.Permissions(kick_members=True)},
        {"managed": True},
    ],
)
def test_never_gives_a_powerful_role(setup, change):
    cog, member, role = setup
    for attr, value in change.items():
        setattr(role, attr, value)
    asyncio.run(cog.on_raw_reaction_add(payload(member=member)))
    member.add_roles.assert_not_awaited()


def test_harmless_permissions_are_fine(setup):
    cog, member, role = setup
    role.permissions = discord.Permissions(send_messages=True, view_channel=True)
    asyncio.run(cog.on_raw_reaction_add(payload(member=member)))
    member.add_roles.assert_awaited_once()
