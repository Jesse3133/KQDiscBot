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
    """
    -- One row per reminder already posted, so it's never posted twice.
    CREATE TABLE sent_reminders (
        guild_id INTEGER NOT NULL,
        event_key TEXT NOT NULL,
        start_ts INTEGER NOT NULL,
        PRIMARY KEY (guild_id, event_key, start_ts)
    );
    -- Bot messages to delete later (reminders when recruitment closes).
    CREATE TABLE pending_deletes (
        message_id INTEGER PRIMARY KEY,
        channel_id INTEGER NOT NULL,
        delete_at INTEGER NOT NULL
    );
    """,
    """
    -- Bot-wide settings changed with /config (e.g. timezone).
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    -- One-off moves of a single occurrence, made with /shift.
    CREATE TABLE shifts (
        event_key TEXT NOT NULL,
        base_start_ts INTEGER NOT NULL,
        minutes INTEGER NOT NULL,
        PRIMARY KEY (event_key, base_start_ts)
    );
    """,
    """
    ALTER TABLE events ADD COLUMN min_level INTEGER;
    ALTER TABLE events ADD COLUMN max_level INTEGER;
    -- Level brackets for the original five Kingdom Quests.
    UPDATE events SET min_level = 17, max_level = 25 WHERE key = 'pirates';
    UPDATE events SET min_level = 33, max_level = 45 WHERE key = 'robo';
    UPDATE events SET min_level = 36, max_level = 65 WHERE key = 'brigade';
    UPDATE events SET min_level = 40, max_level = 50 WHERE key = 'honeying';
    UPDATE events SET min_level = 46, max_level = 60 WHERE key = 'dragon';
    """,
    """
    ALTER TABLE events ADD COLUMN note TEXT NOT NULL DEFAULT '';
    """,
)

EVENT_COLUMNS = (
    "key, name, minute, emoji, interval_hours, first_hour, duration_minutes,"
    " min_level, max_level, note"
)


def _event_values(event: Event) -> tuple:
    return (
        event.key,
        event.name,
        event.minute,
        event.emoji,
        event.interval_hours,
        event.first_hour,
        event.duration_minutes,
        event.min_level,
        event.max_level,
        event.note,
    )


@dataclass(frozen=True)
class PendingDelete:
    message_id: int
    channel_id: int
    delete_at: int  # unix seconds


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
                f"INSERT INTO events ({EVENT_COLUMNS}, position)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(*_event_values(e), position) for position, e in enumerate(events)],
            )

    def add_event(self, event: Event) -> None:
        with self.conn:
            self.conn.execute(
                f"INSERT INTO events ({EVENT_COLUMNS}, position) VALUES"
                " (?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
                " (SELECT COALESCE(MAX(position) + 1, 0) FROM events))",
                _event_values(event),
            )

    def update_event(self, event: Event) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE events SET name = ?, minute = ?, emoji = ?, interval_hours = ?,"
                " first_hour = ?, duration_minutes = ?, min_level = ?, max_level = ?,"
                " note = ? WHERE key = ?",
                (*_event_values(event)[1:], event.key),
            )

    def delete_event(self, key: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM events WHERE key = ?", (key,))
            self.conn.execute("DELETE FROM event_roles WHERE event_key = ?", (key,))
            self.conn.execute("DELETE FROM shifts WHERE event_key = ?", (key,))

    def load_events(self) -> tuple[Event, ...]:
        # Lowest joinable level first; events without levels last, in the order added.
        rows = self.conn.execute(
            f"SELECT {EVENT_COLUMNS} FROM events ORDER BY min_level IS NULL, min_level, position"
        )
        return tuple(Event(**dict(row)) for row in rows)

    # Guilds

    def list_guilds(self) -> list[GuildSettings]:
        return [GuildSettings(**dict(row)) for row in self.conn.execute("SELECT * FROM guilds")]

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

    # Reminders

    def reminder_sent(self, guild_id: int, event_key: str, start_ts: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM sent_reminders WHERE guild_id = ? AND event_key = ? AND start_ts = ?",
            (guild_id, event_key, start_ts),
        ).fetchone()
        return row is not None

    def mark_reminder_sent(self, guild_id: int, event_key: str, start_ts: int) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO sent_reminders VALUES (?, ?, ?)",
                (guild_id, event_key, start_ts),
            )

    def prune_sent_reminders(self, before_ts: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM sent_reminders WHERE start_ts < ?", (before_ts,))

    # Scheduled message deletion

    def schedule_delete(self, item: PendingDelete) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO pending_deletes VALUES (?, ?, ?)",
                (item.message_id, item.channel_id, item.delete_at),
            )

    def due_deletes(self, now_ts: int) -> list[PendingDelete]:
        rows = self.conn.execute(
            "SELECT message_id, channel_id, delete_at FROM pending_deletes"
            " WHERE delete_at <= ? ORDER BY delete_at",
            (now_ts,),
        )
        return [PendingDelete(**dict(row)) for row in rows]

    def remove_pending_delete(self, message_id: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM pending_deletes WHERE message_id = ?", (message_id,))

    # Settings

    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))

    # Shifts

    def load_shifts(self) -> dict[str, dict[int, int]]:
        shifts: dict[str, dict[int, int]] = {}
        for row in self.conn.execute("SELECT event_key, base_start_ts, minutes FROM shifts"):
            shifts.setdefault(row["event_key"], {})[row["base_start_ts"]] = row["minutes"]
        return shifts

    def set_shift(self, event_key: str, base_start_ts: int, minutes: int) -> None:
        """Move one occurrence by ``minutes``; 0 puts it back on its normal time."""
        with self.conn:
            if minutes:
                self.conn.execute(
                    "INSERT OR REPLACE INTO shifts VALUES (?, ?, ?)",
                    (event_key, base_start_ts, minutes),
                )
            else:
                self.conn.execute(
                    "DELETE FROM shifts WHERE event_key = ? AND base_start_ts = ?",
                    (event_key, base_start_ts),
                )

    def prune_shifts(self, before_ts: int) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM shifts WHERE base_start_ts < ?", (before_ts,))
