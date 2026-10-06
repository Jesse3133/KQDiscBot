import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from kqbot.guild_setup import SetupReport, ensure_guild_setup

log = logging.getLogger(__name__)

MISSING_PERMISSIONS = (
    "I'm missing permissions. Make sure my role has **Manage Roles**, **Manage Channels**, "
    "**Send Messages**, **Add Reactions** and **Read Message History**, then run `/setup` again."
)


class SetupCommands(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}
        self._startup_done = False

    async def run_setup(self, guild: discord.Guild) -> SetupReport:
        # One setup at a time per server, e.g. startup and /setup overlapping.
        async with self._locks.setdefault(guild.id, asyncio.Lock()):
            report = await ensure_guild_setup(guild, self.bot.events, self.bot.db)
        log.info("Setup for %s (%s): %s", guild.name, guild.id, report.summary())
        return report

    async def _setup_quietly(self, guild: discord.Guild) -> None:
        try:
            await self.run_setup(guild)
        except discord.Forbidden:
            log.warning("Setup in %s (%s) failed: missing permissions", guild.name, guild.id)
        except Exception:
            log.exception("Setup in %s (%s) failed", guild.name, guild.id)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        # on_ready can fire again after reconnects; only do this once.
        if self._startup_done:
            return
        self._startup_done = True
        reaction_roles = self.bot.get_cog("ReactionRoles")
        for guild in self.bot.guilds:
            if not self.bot.is_allowed(guild.id):
                continue
            # Servers the bot joined before setup existed, or while it was offline.
            if self.bot.db.get_guild(guild.id) is None:
                await self._setup_quietly(guild)
            try:
                await reaction_roles.sync_guild(guild)
            except Exception:
                log.exception("Reaction role catch-up failed in %s", guild.name)

    async def setup_all(self) -> list[str]:
        """Re-run setup everywhere, e.g. after events change. Returns problems."""
        problems = []
        for settings in self.bot.db.list_guilds():
            guild = self.bot.get_guild(settings.guild_id)
            if guild is None or not self.bot.is_allowed(guild.id):
                continue
            try:
                await self.run_setup(guild)
            except discord.Forbidden:
                problems.append(f"{guild.name}: {MISSING_PERMISSIONS}")
            except discord.HTTPException as error:
                log.exception("Setup in %s failed", guild.name)
                problems.append(f"{guild.name}: {error.text or error}")
        return problems

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild) -> None:
        if not self.bot.is_allowed(guild.id):
            log.warning("Added to %s (%s), which isn't allowed; leaving", guild.name, guild.id)
            await guild.leave()
            return
        await self._setup_quietly(guild)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild) -> None:
        self.bot.db.delete_guild(guild.id)

    @app_commands.command(
        name="setup", description="Create or repair the Kingdom Quest roles and channels"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def setup_cmd(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            report = await self.run_setup(interaction.guild)
        except discord.Forbidden:
            await interaction.followup.send(MISSING_PERMISSIONS, ephemeral=True)
            return
        settings = self.bot.db.get_guild(interaction.guild.id)
        await interaction.followup.send(
            f"{report.summary()}\n"
            f"Reminders go to <#{settings.alerts_channel_id}>, "
            f"role picker is in <#{settings.roles_channel_id}>.",
            ephemeral=True,
        )


async def setup(bot) -> None:
    await bot.add_cog(SetupCommands(bot))
