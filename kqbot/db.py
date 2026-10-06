"""SQLite storage for events and per-server setup.

Uses the standard-library sqlite3 module. Every query is tiny, so running
them directly on the bot's event loop is fine.
"""

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from kqbot.events import Event

# Each entry upgrades the schema by one version. Append, never edit.
MIGRATIONS = (
    """
    CREATE TABLE events (
        key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        minute INTEGER NOT NULL,
        emoji TEXT NOT NULL,
        interval_hours INTEGER NOT NULL,
        first_hour INTEGER NOT NULL,
        duration_minutes INTEGER NOT NULL,
        position INTEGER NOT NULL
    );
    CREATE TABLE guilds (
        guild_id INTEGER PRIMARY KEY,
        alerts_channel_id INTEGER,
        roles_channel_id INTEGER,
        roles_message_id INTEGER
    );
    CREATE TABLE event_roles (
        guild_id INTEGER NOT NULL,
        event_key TEXT NOT NULL,
        role_id INTEGER NOT NULL,
        PRIMARY KEY (guild_id, event_key)
    );
    """,
)


@dataclass
class GuildSettings:
    guild_id: int
    alerts_channel_id: int | None = None
    roles_channel_id: int | None = None
    roles_message_id: int | None = None


class Database:
    def __init__(self, path: str | Path) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
            with self.conn:
                self.conn.executescript(script)
                self.conn.execute(f"PRAGMA user_version = {number}")

    # Events

    def seed_events(self, events: Iterable[Event]) -> None:
        """Insert the default events, but only into an empty table."""
        if self.conn.execute("SELECT 1 FROM events LIMIT 1").fetchone():
            return
        with self.conn:
            self.conn.executemany(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        e.key,
                        e.name,
                        e.minute,
                        e.emoji,
                        e.interval_hours,
                        e.first_hour,
                        e.duration_minutes,
                        position,
                    )
                    for position, e in enumerate(events)
                ],
            )

    def load_events(self) -> tuple[Event, ...]:
        rows = self.conn.execute(
            "SELECT key, name, minute, emoji, interval_hours, first_hour, duration_minutes"
            " FROM events ORDER BY position"
        )
        return tuple(Event(**dict(row)) for row in rows)

    # Guilds

    def get_guild(self, guild_id: int) -> GuildSettings | None:
        row = self.conn.execute("SELECT * FROM guilds WHERE guild_id = ?", (guild_id,)).fetchone()
        return GuildSettings(**dict(row)) if row else None

    def save_guild(self, settings: GuildSettings) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO guilds VALUES (?, ?, ?, ?)",
                (
                    settings.guild_id,
                    settings.alerts_channel_id,
                    settings.roles_channel_id,
                    settings.roles_message_id,
                ),
            )

    def delete_guild(self, guild_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM guilds WHERE guild_id = ?", (guild_id,))
            self.conn.execute("DELETE FROM event_roles WHERE guild_id = ?", (guild_id,))

    # Event roles

    def get_event_roles(self, guild_id: int) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT event_key, role_id FROM event_roles WHERE guild_id = ?", (guild_id,)
        )
        return {row["event_key"]: row["role_id"] for row in rows}

    def set_event_role(self, guild_id: int, event_key: str, role_id: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO event_roles VALUES (?, ?, ?)",
                (guild_id, event_key, role_id),
            )
