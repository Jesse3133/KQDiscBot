import asyncio
import logging
import os
import sys
import threading
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
from discord.ext import commands

from kqbot.config import Config
from kqbot.db import Database
from kqbot.events import DEFAULT_EVENTS, Event
from kqbot.schedule import Schedule

log = logging.getLogger(__name__)

EXTENSIONS = (
    "kqbot.cogs.schedule_commands",
    "kqbot.cogs.setup_commands",
    "kqbot.cogs.reaction_roles",
    "kqbot.cogs.reminders",
    "kqbot.cogs.admin_commands",
)


class KQBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        # Default intents only; nothing privileged is needed.
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default())
        self.config = config
        self.db = Database(config.database_path)
        self.db.seed_events(DEFAULT_EVENTS)
        self.events: tuple[Event, ...] = self.db.load_events()
        self.game_tz = self._load_timezone()
        self.db.prune_shifts(int(time.time()) - 24 * 3600)
        self.shifts = self.db.load_shifts()

    def _load_timezone(self) -> ZoneInfo:
        # /config timezone wins over GAME_TIMEZONE in .env.
        name = self.db.get_setting("timezone")
        if name:
            try:
                return ZoneInfo(name)
            except ZoneInfoNotFoundError:
                log.warning("Saved timezone %r is unknown; using %s", name, self.config.game_tz)
        return self.config.game_tz

    @property
    def schedule(self) -> Schedule:
        return Schedule(self.game_tz, self.shifts)

    def reload_events(self) -> None:
        self.events = self.db.load_events()
        self.shifts = self.db.load_shifts()

    async def setup_hook(self) -> None:
        if os.environ.get("KQBOT_SUPERVISED") == "1" and sys.stdin is not None:
            threading.Thread(target=self._stop_when_stdin_closes, daemon=True).start()
        for ext in EXTENSIONS:
            await self.load_extension(ext)

        if self.config.dev_guild_id:
            # Guild commands appear instantly; handy while developing.
            guild = discord.Object(id=self.config.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d command(s) to dev guild %s", len(synced), guild.id)
        else:
            synced = await self.tree.sync()
            log.info("Synced %d global command(s)", len(synced))

    async def on_ready(self) -> None:
        log.info(
            "Logged in as %s (id %s) in %d server(s)", self.user, self.user.id, len(self.guilds)
        )

    def _stop_when_stdin_closes(self) -> None:
        """Shut down when the supervisor closes our stdin or exits.

        That's how the supervisor stops the bot for an update. It also means
        the bot never outlives a supervisor that was killed.
        """
        sys.stdin.buffer.read()
        log.info("Supervisor asked the bot to stop (or exited); shutting down")
        asyncio.run_coroutine_threadsafe(self.close(), self.loop)

    async def close(self) -> None:
        await super().close()
        self.db.close()
