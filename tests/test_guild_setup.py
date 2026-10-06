import asyncio
from dataclasses import replace

import pytest

from kqbot.db import Database
from kqbot.events import DEFAULT_EVENTS, Event
from kqbot.guild_setup import ALERTS_CHANNEL, ROLES_CHANNEL, ensure_guild_setup
from tests.fakes import FakeChannel, FakeGuild, FakeRole


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    yield database
    database.close()


def run(guild, db, events=DEFAULT_EVENTS):
    return asyncio.run(ensure_guild_setup(guild, events, db))


def roles_message(guild, db):
    settings = db.get_guild(guild.id)
    channel = next(c for c in guild.text_channels if c.id == settings.roles_channel_id)
    return channel.messages[settings.roles_message_id]


def test_fresh_server(db):
    guild = FakeGuild()
    report = run(guild, db)

    assert sorted(r.name for r in guild.roles) == sorted(e.name for e in DEFAULT_EVENTS)
    assert all(r.mentionable for r in guild.roles)
    assert [c.name for c in guild.text_channels] == [ALERTS_CHANNEL, ROLES_CHANNEL]
    assert len(report.created) == 5 + 2 + 1

    roles = db.get_event_roles(guild.id)
    assert set(roles) == {e.key for e in DEFAULT_EVENTS}
    message = roles_message(guild, db)
    assert [r.emoji for r in message.reactions] == [e.emoji for e in DEFAULT_EVENTS]
    for event in DEFAULT_EVENTS:
        line = f"{event.emoji} {event.name} ({event.levels}) → <@&{roles[event.key]}>"
        assert line in message.content


def test_new_channels_are_read_only_for_members(db):
    guild = FakeGuild()
    run(guild, db)
    for channel in guild.text_channels:
        everyone = channel.overwrites[guild.default_role]
        assert everyone.send_messages is False
        assert everyone.add_reactions is False
        assert channel.overwrites[guild.me].send_messages is True


def test_second_run_changes_nothing(db):
    guild = FakeGuild()
    run(guild, db)
    message = roles_message(guild, db)

    report = run(guild, db)
    assert report.created == []
    assert report.summary().startswith("Everything was already set up")
    assert len(guild.roles) == 5 and len(guild.text_channels) == 2
    assert roles_message(guild, db) is message
    assert message.edits == 0 and len(message.reactions) == 5


def test_recreates_deleted_channel_and_message(db):
    guild = FakeGuild()
    run(guild, db)
    guild.text_channels = [c for c in guild.text_channels if c.name != ROLES_CHANNEL]

    report = run(guild, db)
    assert report.created == [
        f"channel #{ROLES_CHANNEL}",
        f"role picker message in #{ROLES_CHANNEL}",
    ]
    assert len(roles_message(guild, db).reactions) == 5


def test_recreates_deleted_role(db):
    guild = FakeGuild()
    run(guild, db)
    honeying_id = db.get_event_roles(guild.id)["honeying"]
    guild.roles = [r for r in guild.roles if r.id != honeying_id]

    report = run(guild, db)
    assert report.created == ["role @Mean Giant Honeying"]
    new_id = db.get_event_roles(guild.id)["honeying"]
    assert new_id != honeying_id
    assert f"<@&{new_id}>" in roles_message(guild, db).content


def test_reuses_existing_roles_and_channels_by_name(db):
    guild = FakeGuild(
        roles=[FakeRole("Mean Giant Honeying")],
        text_channels=[FakeChannel(ALERTS_CHANNEL)],
    )
    existing_role, existing_channel = guild.roles[0], guild.text_channels[0]
    run(guild, db)
    assert db.get_event_roles(guild.id)["honeying"] == existing_role.id
    assert db.get_guild(guild.id).alerts_channel_id == existing_channel.id
    assert len(guild.roles) == 5 and len(guild.text_channels) == 2


def test_message_updated_when_events_change(db):
    guild = FakeGuild()
    run(guild, db)
    extra = Event(key="new", name="New Quest", minute=20, emoji="⭐")

    run(guild, db, events=(*DEFAULT_EVENTS, extra))
    message = roles_message(guild, db)
    assert message.edits == 1
    assert "⭐ New Quest" in message.content
    assert [r.emoji for r in message.reactions][-1] == "⭐"


def test_renamed_event_renames_role(db):
    guild = FakeGuild()
    run(guild, db)
    role_id = db.get_event_roles(guild.id)["honeying"]
    renamed = tuple(
        replace(e, name="Honey Time") if e.key == "honeying" else e for e in DEFAULT_EVENTS
    )
    report = run(guild, db, events=renamed)
    assert report.created == ["renamed @Mean Giant Honeying to @Honey Time"]
    assert guild.get_role(role_id).name == "Honey Time"
    assert len(guild.roles) == 5


def test_changed_emoji_swaps_reaction_in_place(db):
    guild = FakeGuild()
    run(guild, db)
    changed = tuple(replace(e, emoji="🐝") if e.key == "honeying" else e for e in DEFAULT_EVENTS)
    run(guild, db, events=changed)
    # A new emoji can only go at the end, so the picker is reposted in order.
    assert [r.emoji for r in roles_message(guild, db).reactions] == [e.emoji for e in changed]


def test_removed_event_drops_reaction(db):
    guild = FakeGuild()
    run(guild, db)
    fewer = tuple(e for e in DEFAULT_EVENTS if e.key != "honeying")
    run(guild, db, events=fewer)
    message = roles_message(guild, db)
    assert "🍯" not in [r.emoji for r in message.reactions]
    assert "Mean Giant Honeying" not in message.content


def test_custom_emoji_reaction(db):
    guild = FakeGuild()
    custom = Event(key="c", name="Custom", minute=5, emoji="<:honey:123456789012345678>")
    run(guild, db, events=(custom,))
    assert [r.emoji for r in roles_message(guild, db).reactions] == ["<:honey:123456789012345678>"]
    # Running again doesn't add it twice.
    run(guild, db, events=(custom,))
    assert len(roles_message(guild, db).reactions) == 1


def test_picker_lists_events_by_lowest_level(db):
    guild = FakeGuild()
    run(guild, db)
    lines = roles_message(guild, db).content.splitlines()[3:]
    assert [line.split(" (Lv")[0] for line in lines] == [
        "🏴‍☠️ Mara Pirates' Rage",
        "🤖 The Millennium Robo Plot",
        "🌙 Midnight Brigade Veteran",
        "🍯 Mean Giant Honeying",
        "🐉 Mini Dragon HC",
    ]
    assert "(Lv 17-25)" in lines[0] and "(Lv 46-60)" in lines[4]


def test_new_order_reposts_picker(db):
    guild = FakeGuild()
    old_order = tuple(sorted(DEFAULT_EVENTS, key=lambda e: e.minute))  # time order
    run(guild, db, events=old_order)
    old_message = roles_message(guild, db)

    report = run(guild, db)  # level order
    new_message = roles_message(guild, db)
    assert new_message is not old_message and old_message.deleted
    assert [r.emoji for r in new_message.reactions] == [e.emoji for e in DEFAULT_EVENTS]
    assert report.created == [f"reposted role picker in #{ROLES_CHANNEL} (new order)"]


def test_adding_last_event_does_not_repost(db):
    guild = FakeGuild()
    run(guild, db)
    message = roles_message(guild, db)
    high = Event(key="new", name="High", minute=20, emoji="⭐", min_level=100, max_level=110)
    run(guild, db, events=(*DEFAULT_EVENTS, high))
    assert roles_message(guild, db) is message and not message.deleted


def test_adding_event_in_the_middle_reposts(db):
    guild = FakeGuild()
    run(guild, db)
    message = roles_message(guild, db)
    mid = Event(key="mid", name="Mid", minute=20, emoji="⭐", min_level=20, max_level=30)
    events = (DEFAULT_EVENTS[0], mid, *DEFAULT_EVENTS[1:])
    run(guild, db, events=events)
    assert message.deleted
    assert [r.emoji for r in roles_message(guild, db).reactions] == [e.emoji for e in events]
