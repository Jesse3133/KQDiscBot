from dataclasses import replace

import pytest

from kqbot.db import MIGRATIONS, Database, GuildSettings
from kqbot.events import DEFAULT_EVENTS


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.sqlite3")
    yield database
    database.close()


def test_migrates_to_latest(db):
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)


def test_reopening_keeps_data(tmp_path):
    path = tmp_path / "test.sqlite3"
    first = Database(path)
    first.seed_events(DEFAULT_EVENTS)
    first.close()
    second = Database(path)
    assert second.load_events() == DEFAULT_EVENTS
    second.close()


def test_seed_then_load_in_order(db):
    db.seed_events(DEFAULT_EVENTS)
    assert db.load_events() == DEFAULT_EVENTS


def test_seed_does_not_overwrite_existing(db):
    db.seed_events(DEFAULT_EVENTS[:1])
    db.seed_events([replace(DEFAULT_EVENTS[0], minute=59), *DEFAULT_EVENTS[1:]])
    assert db.load_events() == DEFAULT_EVENTS[:1]


def test_guild_round_trip(db):
    assert db.get_guild(1) is None
    db.save_guild(GuildSettings(1, alerts_channel_id=10))
    db.save_guild(GuildSettings(1, alerts_channel_id=10, roles_channel_id=20, roles_message_id=30))
    assert db.get_guild(1) == GuildSettings(1, 10, 20, 30)


def test_event_roles(db):
    db.set_event_role(1, "honeying", 100)
    db.set_event_role(1, "honeying", 101)
    db.set_event_role(1, "dragon", 200)
    db.set_event_role(2, "dragon", 300)
    assert db.get_event_roles(1) == {"honeying": 101, "dragon": 200}


def test_delete_guild(db):
    db.save_guild(GuildSettings(1, 10))
    db.set_event_role(1, "honeying", 100)
    db.set_event_role(2, "honeying", 200)
    db.delete_guild(1)
    assert db.get_guild(1) is None
    assert db.get_event_roles(1) == {}
    assert db.get_event_roles(2) == {"honeying": 200}
