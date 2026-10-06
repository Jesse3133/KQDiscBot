import logging

import discord
from discord.ext import commands

from kqbot.config import Config
from kqbot.db import Database
from kqbot.events import DEFAULT_EVENTS, Event

log = logging.getLogger(__name__)

EXTENSIONS = (
    "kqbot.cogs.schedule_commands",
    "kqbot.cogs.setup_commands",
    "kqbot.cogs.reaction_roles",
    "kqbot.cogs.reminders",
)


class KQBot(commands.Bot):
    def __init__(self, config: Config) -> None:
        # Default intents only; nothing privileged is needed.
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default())
        self.config = config
        self.db = Database(config.database_path)
        self.db.seed_events(DEFAULT_EVENTS)
        self.events: tuple[Event, ...] = self.db.load_events()

    async def setup_hook(self) -> None:
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

    async def close(self) -> None:
        await super().close()
        self.db.close()
