"""Admin commands: /event, /shift and /config. All need Manage Server."""

import logging
from dataclasses import replace
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

import discord
from discord import app_commands
from discord.ext import commands

from kqbot.cogs.common import event_choices
from kqbot.cogs.reminders import find_problems
from kqbot.events import (
    MAX_EVENTS,
    MAX_LEVEL,
    Event,
    custom_emoji_id,
    make_key,
    normalize_emoji,
)
from kqbot.formatting import describe_event, next_line, ts
from kqbot.reminders import REMINDER_LEAD
from kqbot.schedule import MAX_SHIFT_MINUTES

log = logging.getLogger(__name__)

ADMIN = discord.Permissions(manage_guild=True)
ALL_EVENTS = "*"
INTERVALS = [
    app_commands.Choice(name="every hour", value=1),
    app_commands.Choice(name="every 2 hours", value=2),
    app_commands.Choice(name="every 3 hours", value=3),
    app_commands.Choice(name="every 4 hours", value=4),
    app_commands.Choice(name="every 6 hours", value=6),
    app_commands.Choice(name="every 8 hours", value=8),
    app_commands.Choice(name="every 12 hours", value=12),
    app_commands.Choice(name="once a day", value=24),
]
COMMON_TIMEZONES = ("America/Los_Angeles", "UTC", "America/New_York", "Europe/London")
NEEDS_SETUP = "This server isn't set up yet. Run `/setup` first."


class ConfirmView(discord.ui.View):
    def __init__(self, user_id: int, label: str) -> None:
        super().__init__(timeout=60)
        self.user_id = user_id
        self.confirmed = False
        self.confirm.label = label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.confirmed = True
        await interaction.response.edit_message(content="Working on it…", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        await interaction.response.edit_message(content="Cancelled. Nothing changed.", view=None)
        self.stop()


class AdminCommands(commands.Cog):
    event = app_commands.Group(
        name="event",
        description="Add, change or remove Kingdom Quests",
        default_permissions=ADMIN,
        guild_only=True,
    )
    config = app_commands.Group(
        name="config",
        description="Bot settings",
        default_permissions=ADMIN,
        guild_only=True,
    )

    def __init__(self, bot) -> None:
        self.bot = bot

    # Helpers

    def _find(self, key: str) -> Event | None:
        return next((e for e in self.bot.events if e.key == key), None)

    async def _emoji_problem(self, emoji: str, ignore_key: str | None = None) -> str | None:
        """Why this emoji can't be used for an event, or None if it's fine."""
        if any(
            normalize_emoji(e.emoji) == normalize_emoji(emoji) and e.key != ignore_key
            for e in self.bot.events
        ):
            return "Another event already uses that emoji. Each event needs its own."
        custom_id = custom_emoji_id(emoji)
        if custom_id is None:
            return None
        if self.bot.get_emoji(custom_id) is not None:
            return None
        try:
            app_emojis = await self.bot.fetch_application_emojis()
        except discord.HTTPException:
            app_emojis = []
        if any(e.id == custom_id for e in app_emojis):
            return None
        return (
            "I can't use that custom emoji. Upload it on the bot's **Emojis** page in the "
            "Developer Portal, or use an emoji from a server I'm in."
        )

    def _name_taken(self, name: str, ignore_key: str | None = None) -> bool:
        return any(
            e.name.casefold() == name.strip().casefold() and e.key != ignore_key
            for e in self.bot.events
        )

    async def _apply(self, interaction: discord.Interaction, summary: str) -> None:
        """Reload events, update every server's roles and picker, then reply."""
        self.bot.reload_events()
        problems = await self.bot.get_cog("SetupCommands").setup_all()
        if problems:
            summary += "\n\n**Couldn't update everything:**\n" + "\n".join(
                f"• {p}" for p in problems
            )
        await interaction.followup.send(summary, ephemeral=True)

    # /event

    @event.command(name="list", description="Show every event and its timing")
    async def event_list(self, interaction: discord.Interaction) -> None:
        lines = [describe_event(e) for e in self.bot.events] or ["No events yet."]
        lines.append(f"\nTimes are in `{self.bot.game_tz.key}`.")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @event.command(name="add", description="Add a new event")
    @app_commands.describe(
        name="Event name; also used for its ping role",
        minute="Minute past the hour it starts (0-59)",
        emoji="Emoji for the role picker; custom emojis work too",
        interval="How often it repeats (default every 2 hours)",
        first_hour="Any hour it starts at, in game time (0-23). Default 1 = odd hours",
        duration="Recruitment length in minutes (default 30)",
        min_level="Lowest level that can join (set with max_level)",
        max_level="Highest level that can join (set with min_level)",
    )
    @app_commands.choices(interval=INTERVALS)
    async def event_add(
        self,
        interaction: discord.Interaction,
        name: str,
        minute: app_commands.Range[int, 0, 59],
        emoji: str,
        interval: app_commands.Choice[int] | None = None,
        first_hour: app_commands.Range[int, 0, 23] = 1,
        duration: app_commands.Range[int, 1, 1440] = 30,
        min_level: app_commands.Range[int, 1, MAX_LEVEL] | None = None,
        max_level: app_commands.Range[int, 1, MAX_LEVEL] | None = None,
    ) -> None:
        if len(self.bot.events) >= MAX_EVENTS:
            await interaction.response.send_message(
                f"There can be at most {MAX_EVENTS} events (Discord's reaction limit).",
                ephemeral=True,
            )
            return
        if self._name_taken(name):
            await interaction.response.send_message(
                "An event with that name already exists.", ephemeral=True
            )
            return
        try:
            new = Event(
                key=make_key(name, {e.key for e in self.bot.events}),
                name=name.strip(),
                minute=minute,
                emoji=emoji.strip(),
                interval_hours=interval.value if interval else 2,
                first_hour=first_hour,
                duration_minutes=duration,
                min_level=min_level,
                max_level=max_level,
            )
        except ValueError as error:
            await interaction.response.send_message(f"Can't add that: {error}.", ephemeral=True)
            return
        if problem := await self._emoji_problem(new.emoji):
            await interaction.response.send_message(problem, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        self.bot.db.add_event(new)
        next_start = self.bot.schedule.next(new, datetime.now(UTC)).start
        await self._apply(
            interaction,
            f"Added {describe_event(new)}.\nNext start: {ts(next_start, 'f')}.\n"
            "Its role and role picker emoji have been added.",
        )

    @event.command(name="edit", description="Change an event. Only the options you fill in change")
    @app_commands.describe(
        event="Event to change",
        name="New name (its role is renamed too)",
        minute="New minute past the hour (0-59)",
        emoji="New emoji for the role picker",
        interval="New repeat interval",
        first_hour="Any hour it starts at, in game time (0-23)",
        duration="New recruitment length in minutes",
        min_level="Lowest level that can join. 0 (with max_level 0) removes the range",
        max_level="Highest level that can join. 0 (with min_level 0) removes the range",
    )
    @app_commands.choices(interval=INTERVALS)
    async def event_edit(
        self,
        interaction: discord.Interaction,
        event: str,
        name: str | None = None,
        minute: app_commands.Range[int, 0, 59] | None = None,
        emoji: str | None = None,
        interval: app_commands.Choice[int] | None = None,
        first_hour: app_commands.Range[int, 0, 23] | None = None,
        duration: app_commands.Range[int, 1, 1440] | None = None,
        min_level: app_commands.Range[int, 0, MAX_LEVEL] | None = None,
        max_level: app_commands.Range[int, 0, MAX_LEVEL] | None = None,
    ) -> None:
        old = self._find(event)
        if old is None:
            await interaction.response.send_message(
                "I don't know that event. Pick one from the list.", ephemeral=True
            )
            return
        changes = {
            "name": name.strip() if name else None,
            "minute": minute,
            "emoji": emoji.strip() if emoji else None,
            "interval_hours": interval.value if interval else None,
            "first_hour": first_hour,
            "duration_minutes": duration,
        }
        changes = {k: v for k, v in changes.items() if v is not None}
        # Levels: 0 means "no range", so map it to None after filtering.
        if min_level is not None:
            changes["min_level"] = min_level or None
        if max_level is not None:
            changes["max_level"] = max_level or None
        if not changes:
            await interaction.response.send_message(
                "Nothing to change. Fill in at least one option.", ephemeral=True
            )
            return
        if "name" in changes and self._name_taken(changes["name"], ignore_key=old.key):
            await interaction.response.send_message(
                "Another event already has that name.", ephemeral=True
            )
            return
        try:
            new = replace(old, **changes)
        except ValueError as error:
            await interaction.response.send_message(f"Can't change that: {error}.", ephemeral=True)
            return
        if "emoji" in changes and (
            problem := await self._emoji_problem(new.emoji, ignore_key=old.key)
        ):
            await interaction.response.send_message(problem, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        self.bot.db.update_event(new)
        note = ""
        if "emoji" in changes:
            note = (
                "\nPeople keep the roles they have. To drop the role later they react "
                "with the new emoji and remove it again."
            )
        await self._apply(interaction, f"Updated. Now: {describe_event(new)}.{note}")

    @event.command(name="remove", description="Remove an event and delete its role")
    @app_commands.describe(event="Event to remove")
    async def event_remove(self, interaction: discord.Interaction, event: str) -> None:
        old = self._find(event)
        if old is None:
            await interaction.response.send_message(
                "I don't know that event. Pick one from the list.", ephemeral=True
            )
            return
        view = ConfirmView(interaction.user.id, label=f"Remove {old.name}")
        await interaction.response.send_message(
            f"Remove **{old.name}**? Its reminders stop and its role is deleted, "
            "which takes it away from everyone who has it.",
            view=view,
            ephemeral=True,
        )
        timed_out = await view.wait()
        if not view.confirmed:
            if timed_out:  # the Cancel button already updated the message itself
                await interaction.edit_original_response(
                    content="Timed out. Nothing changed.", view=None
                )
            return

        problems = []
        for settings in self.bot.db.list_guilds():
            guild = self.bot.get_guild(settings.guild_id)
            role_id = self.bot.db.get_event_roles(settings.guild_id).get(old.key)
            role = guild.get_role(role_id) if guild and role_id else None
            if role is None:
                continue
            try:
                await role.delete(reason=f"Event {old.name} removed")
            except discord.HTTPException:
                problems.append(
                    f"Couldn't delete {role.mention} in {guild.name}; delete it by hand."
                )
        self.bot.db.delete_event(old.key)
        self.bot.reload_events()
        problems += await self.bot.get_cog("SetupCommands").setup_all()

        text = f"Removed **{old.name}**."
        if problems:
            text += "\n\n" + "\n".join(f"• {p}" for p in problems)
        await interaction.edit_original_response(content=text)

    @event_edit.autocomplete("event")
    @event_remove.autocomplete("event")
    async def event_autocomplete(self, interaction: discord.Interaction, current: str):
        return event_choices(self.bot.events, current)

    # /shift

    @app_commands.command(
        name="shift", description="Move just the next start of an event, e.g. for maintenance"
    )
    @app_commands.describe(
        event="Event to move, or all events",
        minutes="Minutes later than normal (negative = earlier). 0 puts it back to normal",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def shift(
        self,
        interaction: discord.Interaction,
        event: str,
        minutes: app_commands.Range[int, -MAX_SHIFT_MINUTES, MAX_SHIFT_MINUTES],
    ) -> None:
        targets = list(self.bot.events) if event == ALL_EVENTS else [self._find(event)]
        if not targets or targets[0] is None:
            await interaction.response.send_message(
                "I don't know that event. Pick one from the list.", ephemeral=True
            )
            return

        now = datetime.now(UTC)
        schedule = self.bot.schedule
        lines, skipped = [], []
        for target in targets:
            occ = schedule.next(target, now)
            base = occ.base_start
            new_start = base.timestamp() + minutes * 60
            if new_start <= now.timestamp():
                skipped.append(target.name)
                continue
            self.bot.db.set_shift(target.key, int(base.timestamp()), minutes)
            new = datetime.fromtimestamp(new_start, UTC)
            if minutes:
                lines.append(
                    f"{target.emoji} **{target.name}** now starts {ts(new, 't')} "
                    f"({ts(new, 'R')}), normally {ts(base, 't')}"
                )
            else:
                lines.append(f"{target.emoji} **{target.name}** back to normal: {ts(base, 't')}")
        self.bot.shifts = self.bot.db.load_shifts()

        if lines:
            lines.append(
                "\nOnly this one start is affected. For a permanent change use `/event edit`."
            )
        if skipped:
            lines.append("Not moved, it would be in the past: " + ", ".join(skipped))
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @shift.autocomplete("event")
    async def shift_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = event_choices(self.bot.events, current)
        if current.lower() in "all events":
            choices.insert(0, app_commands.Choice(name="All events", value=ALL_EVENTS))
        return choices[:25]

    # /config

    @config.command(name="show", description="Show the current settings")
    async def config_show(self, interaction: discord.Interaction) -> None:
        settings = self.bot.db.get_guild(interaction.guild.id)

        def channel(channel_id: int | None) -> str:
            return f"<#{channel_id}>" if channel_id else "not set (run `/setup`)"

        minutes = int(REMINDER_LEAD.total_seconds() // 60)
        tz_source = "set with /config" if self.bot.db.get_setting("timezone") else "from .env"
        await interaction.response.send_message(
            "\n".join(
                [
                    f"**Game time zone:** `{self.bot.game_tz.key}` ({tz_source})",
                    f"**Reminders channel:** {channel(settings and settings.alerts_channel_id)}",
                    f"**Role picker channel:** {channel(settings and settings.roles_channel_id)}",
                    f"**Reminder time:** {minutes} minutes before the start",
                    f"**Events:** {len(self.bot.events)} (see `/event list`)",
                ]
            ),
            ephemeral=True,
        )

    @config.command(name="alerts-channel", description="Choose where reminders are posted")
    @app_commands.describe(channel="Channel for reminders")
    async def config_alerts(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        settings = self.bot.db.get_guild(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message(NEEDS_SETUP, ephemeral=True)
            return
        if problems := find_problems(channel, [], {}):
            await interaction.response.send_message(
                "I can't use that channel:\n" + "\n".join(f"• {p}" for p in problems),
                ephemeral=True,
            )
            return
        settings.alerts_channel_id = channel.id
        self.bot.db.save_guild(settings)
        await interaction.response.send_message(
            f"Reminders will be posted in {channel.mention}. Try `/test-reminder` to check.",
            ephemeral=True,
        )

    @config.command(name="roles-channel", description="Move the role picker to another channel")
    @app_commands.describe(channel="Channel for the role picker message")
    async def config_roles(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ) -> None:
        settings = self.bot.db.get_guild(interaction.guild.id)
        if settings is None:
            await interaction.response.send_message(NEEDS_SETUP, ephemeral=True)
            return
        if problems := find_problems(channel, [], {}):
            await interaction.response.send_message(
                "I can't use that channel:\n" + "\n".join(f"• {p}" for p in problems),
                ephemeral=True,
            )
            return
        if channel.id == settings.roles_channel_id:
            await interaction.response.send_message(
                "The role picker is already there.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        old_channel = interaction.guild.get_channel(settings.roles_channel_id or 0)
        if old_channel is not None and settings.roles_message_id:
            try:
                await old_channel.get_partial_message(settings.roles_message_id).delete()
            except discord.HTTPException:
                pass  # already gone; nothing to clean up
        settings.roles_channel_id = channel.id
        settings.roles_message_id = None
        self.bot.db.save_guild(settings)
        await self.bot.get_cog("SetupCommands").run_setup(interaction.guild)
        await interaction.followup.send(
            f"The role picker is now in {channel.mention}. People keep the roles they have.",
            ephemeral=True,
        )

    @config.command(name="timezone", description="Set the time zone the game schedules events in")
    @app_commands.describe(name="IANA time zone, e.g. America/Los_Angeles or UTC")
    async def config_timezone(self, interaction: discord.Interaction, name: str) -> None:
        try:
            tz = ZoneInfo(name.strip())
        except (ZoneInfoNotFoundError, ValueError):
            await interaction.response.send_message(
                f"`{name}` isn't a time zone I know. Pick one from the list.", ephemeral=True
            )
            return
        self.bot.db.set_setting("timezone", tz.key)
        self.bot.game_tz = tz
        now = datetime.now(UTC)
        schedule = self.bot.schedule
        soonest = min(
            (schedule.next(e, now) for e in self.bot.events),
            key=lambda occ: occ.start,
            default=None,
        )
        text = f"Game time zone is now `{tz.key}`."
        if soonest is not None:
            text += f"\nNext up: {next_line(soonest, None)}"
        await interaction.response.send_message(text, ephemeral=True)

    @config_timezone.autocomplete("name")
    async def timezone_autocomplete(self, interaction: discord.Interaction, current: str):
        current = current.lower()
        if not current:
            names = list(COMMON_TIMEZONES)
        else:
            names = sorted(z for z in available_timezones() if current in z.lower())
        return [app_commands.Choice(name=z, value=z) for z in names[:25]]


async def setup(bot) -> None:
    await bot.add_cog(AdminCommands(bot))
