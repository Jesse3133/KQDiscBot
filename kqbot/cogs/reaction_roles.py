"""Gives or removes an event role when someone reacts on the role picker message."""

import logging

import discord
from discord.ext import commands

from kqbot.events import find_event_by_emoji

log = logging.getLogger(__name__)


class ReactionRoles(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    # Raw events fire even when the message isn't in the bot's cache,
    # e.g. after a restart.
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        await self._handle(payload, add=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent) -> None:
        await self._handle(payload, add=False)

    async def _handle(self, payload: discord.RawReactionActionEvent, add: bool) -> None:
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return
        settings = self.bot.db.get_guild(payload.guild_id)
        if settings is None or settings.roles_message_id != payload.message_id:
            return
        event = find_event_by_emoji(self.bot.events, str(payload.emoji))
        guild = self.bot.get_guild(payload.guild_id)
        if event is None or guild is None:
            return

        role_id = self.bot.db.get_event_roles(guild.id).get(event.key)
        role = guild.get_role(role_id) if role_id else None
        if role is None:
            log.warning("Role for %s is missing in %s; run /setup", event.name, guild.name)
            return

        member = payload.member if add else await self._get_member(guild, payload.user_id)
        if member is None or member.bot:
            return

        try:
            if add:
                await member.add_roles(role, reason="Kingdom Quest role picker")
            else:
                await member.remove_roles(role, reason="Kingdom Quest role picker")
        except discord.Forbidden:
            log.warning(
                "Can't change role %s in %s: my role must be above it and have Manage Roles",
                role.name,
                guild.name,
            )

    async def sync_guild(self, guild: discord.Guild) -> int:
        """Give roles for reactions added while the bot was offline.

        Returns how many roles were given. Removals made while offline can't
        be detected without the privileged members intent, so those wait
        until the person reacts and un-reacts again.
        """
        settings = self.bot.db.get_guild(guild.id)
        if settings is None or not settings.roles_message_id:
            return 0
        channel = guild.get_channel(settings.roles_channel_id)
        if channel is None:
            return 0
        try:
            message = await channel.fetch_message(settings.roles_message_id)
        except (discord.NotFound, discord.Forbidden):
            return 0

        role_ids = self.bot.db.get_event_roles(guild.id)
        given = 0
        for reaction in message.reactions:
            event = find_event_by_emoji(self.bot.events, str(reaction.emoji))
            role = guild.get_role(role_ids.get(event.key, 0)) if event else None
            if role is None:
                continue
            async for user in reaction.users():
                if user.bot:
                    continue
                member = await self._get_member(guild, user.id)
                if member is None or role in member.roles:
                    continue
                try:
                    await member.add_roles(role, reason="Kingdom Quest role picker (catch-up)")
                    given += 1
                except discord.Forbidden:
                    log.warning("Can't give %s in %s: check role order", role.name, guild.name)
                    break
        if given:
            log.info("Gave %d role(s) for reactions made while offline in %s", given, guild.name)
        return given

    @staticmethod
    async def _get_member(guild: discord.Guild, user_id: int) -> discord.Member | None:
        # Reaction removals don't include the member, and without the
        # privileged members intent the cache is sparse, so ask the API.
        member = guild.get_member(user_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(user_id)
        except discord.NotFound:
            return None


async def setup(bot) -> None:
    await bot.add_cog(ReactionRoles(bot))
