"""Posts "starting soon" reminders, pings event roles, and cleans them up."""

import logging
from datetime import UTC, datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from kqbot.cogs.common import event_choices
from kqbot.db import GuildSettings, PendingDelete
from kqbot.events import Event
from kqbot.formatting import reminder_message
from kqbot.reminders import REMINDER_LEAD, TEST_LIFETIME, due_reminders
from kqbot.schedule import Occurrence

log = logging.getLogger(__name__)

ATTENDANCE_EMOJIS = ("✅", "❌")
CHECK_EVERY_SECONDS = 10


async def send_reminder(
    channel: discord.abc.Messageable,
    occ: Occurrence,
    role: discord.Role | None,
    test: bool = False,
    extra: str = "",
) -> discord.Message:
    message = await channel.send(
        reminder_message(occ, role.id if role else None, test=test, extra=extra),
        # Ping only the event role, never @everyone or users.
        allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=True),
    )
    for emoji in ATTENDANCE_EMOJIS:
        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            log.warning("Couldn't add %s to reminder in #%s", emoji, channel)
    return message


def find_problems(
    channel: discord.TextChannel, events: list[Event], roles: dict[str, discord.Role | None]
) -> list[str]:
    """Things that would stop reminders from posting or pinging."""
    problems = []
    perms = channel.permissions_for(channel.guild.me)
    for name, ok in (
        ("View Channel", perms.view_channel),
        ("Send Messages", perms.send_messages),
        ("Add Reactions", perms.add_reactions),
        ("Read Message History", perms.read_message_history),
    ):
        if not ok:
            problems.append(f"I don't have **{name}** in {channel.mention}.")
    for event in events:
        role = roles.get(event.key)
        if role is None:
            problems.append(f"The role for **{event.name}** is missing. Run `/setup`.")
        elif not role.mentionable and not perms.mention_everyone:
            problems.append(
                f"{role.mention} isn't mentionable, so pings won't notify anyone. "
                "Turn on *Allow anyone to @mention this role* in its role settings."
            )
    return problems


class Reminders(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    def reminder_text(self) -> str:
        """Shared text for every reminder, set with /config reminder-text."""
        return self.bot.db.get_setting("reminder_text") or ""

    async def cog_load(self) -> None:
        self.check.start()

    async def cog_unload(self) -> None:
        self.check.cancel()

    @tasks.loop(seconds=CHECK_EVERY_SECONDS)
    async def check(self) -> None:
        # An unhandled error would stop the loop for good, so catch everything.
        try:
            await self.tick(datetime.now(UTC))
        except Exception:
            log.exception("Reminder check failed")

    @check.before_loop
    async def before_check(self) -> None:
        await self.bot.wait_until_ready()

    async def tick(self, now: datetime) -> None:
        await self.delete_expired(now)
        due = due_reminders(self.bot.events, now, self.bot.schedule)
        for settings in self.bot.db.list_guilds():
            if not self.bot.is_allowed(settings.guild_id):
                continue
            for occ in due:
                start_ts = int(occ.start.timestamp())
                if self.bot.db.reminder_sent(settings.guild_id, occ.event.key, start_ts):
                    continue
                # Mark first: if posting fails we log it rather than retry every 10 s.
                self.bot.db.mark_reminder_sent(settings.guild_id, occ.event.key, start_ts)
                await self.post(settings, occ)
        self.bot.db.prune_sent_reminders(int((now - timedelta(days=1)).timestamp()))

    async def post(self, settings: GuildSettings, occ: Occurrence) -> None:
        guild = self.bot.get_guild(settings.guild_id)
        if guild is None:
            return
        channel = guild.get_channel(settings.alerts_channel_id)
        if channel is None:
            log.warning("Alerts channel missing in %s; run /setup", guild.name)
            return
        role_id = self.bot.db.get_event_roles(guild.id).get(occ.event.key)
        role = guild.get_role(role_id) if role_id else None
        if role is None:
            log.warning("Role for %s missing in %s; posting without a ping", occ.event.name, guild)
        try:
            message = await send_reminder(channel, occ, role, extra=self.reminder_text())
        except discord.HTTPException:
            log.exception("Couldn't post %s reminder in %s", occ.event.name, guild.name)
            return
        self.bot.db.schedule_delete(PendingDelete(message.id, channel.id, int(occ.end.timestamp())))

    async def delete_expired(self, now: datetime) -> None:
        for item in self.bot.db.due_deletes(int(now.timestamp())):
            channel = self.bot.get_partial_messageable(item.channel_id)
            try:
                await channel.get_partial_message(item.message_id).delete()
            except (discord.NotFound, discord.Forbidden):
                pass  # already gone, or the channel is; nothing more to do
            except discord.HTTPException:
                log.warning("Couldn't delete reminder %s; will retry", item.message_id)
                continue
            self.bot.db.remove_pending_delete(item.message_id)

    @app_commands.command(
        name="test-reminder",
        description="Post a test reminder that pings event roles, to check everything works",
    )
    @app_commands.describe(event="Only test this event (default: all of them)")
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def test_reminder(self, interaction: discord.Interaction, event: str | None = None):
        guild = interaction.guild
        settings = self.bot.db.get_guild(guild.id)
        channel = guild.get_channel(settings.alerts_channel_id) if settings else None
        if channel is None:
            await interaction.response.send_message(
                "I can't find the alerts channel. Run `/setup` first.", ephemeral=True
            )
            return

        events = [e for e in self.bot.events if event is None or e.key == event]
        if not events:
            await interaction.response.send_message(
                "I don't know that event. Pick one from the list.", ephemeral=True
            )
            return

        role_ids = self.bot.db.get_event_roles(guild.id)
        roles = {e.key: guild.get_role(role_ids.get(e.key, 0)) for e in events}
        problems = find_problems(channel, events, roles)
        perms = channel.permissions_for(guild.me)
        if not (perms.view_channel and perms.send_messages):
            await interaction.response.send_message(
                "Couldn't post a test:\n" + "\n".join(f"• {p}" for p in problems), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        now = datetime.now(UTC)
        delete_at = int((now + TEST_LIFETIME).timestamp())
        for e in events:
            occ = Occurrence(e, now + REMINDER_LEAD)  # pretend it starts in 3 minutes
            message = await send_reminder(
                channel, occ, roles[e.key], test=True, extra=self.reminder_text()
            )
            self.bot.db.schedule_delete(PendingDelete(message.id, channel.id, delete_at))

        minutes = int(TEST_LIFETIME.total_seconds() // 60)
        lines = [
            f"Posted {len(events)} test reminder(s) in {channel.mention}. "
            f"They delete themselves in {minutes} minutes.",
            "You'll only get a notification for roles you have.",
        ]
        if problems:
            lines += ["", "**Problems found:**", *(f"• {p}" for p in problems)]
        else:
            lines.append("No problems found.")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @test_reminder.autocomplete("event")
    async def event_autocomplete(self, interaction: discord.Interaction, current: str):
        return event_choices(self.bot.events, current)


async def setup(bot) -> None:
    await bot.add_cog(Reminders(bot))
