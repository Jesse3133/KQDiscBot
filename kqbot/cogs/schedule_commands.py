from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from kqbot.formatting import next_line
from kqbot.schedule import current_occurrence, next_occurrence


class ScheduleCommands(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot

    @app_commands.command(name="next", description="When do Kingdom Quests start next?")
    @app_commands.describe(event="Only show this event")
    async def next_cmd(self, interaction: discord.Interaction, event: str | None = None) -> None:
        events = self.bot.events
        if event is not None:
            events = [e for e in events if e.key == event]
            if not events:
                await interaction.response.send_message(
                    "I don't know that event. Pick one from the list.", ephemeral=True
                )
                return

        now = datetime.now(UTC)
        tz = self.bot.config.game_tz
        rows = sorted(
            ((next_occurrence(e, now, tz), current_occurrence(e, now, tz)) for e in events),
            # Open recruitment first, then soonest start.
            key=lambda pair: (pair[1] is None, pair[0].start),
        )
        lines = [next_line(upcoming, active) for upcoming, active in rows]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @next_cmd.autocomplete("event")
    async def event_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        current = current.lower()
        return [
            app_commands.Choice(name=e.name, value=e.key)
            for e in self.bot.events
            if current in e.name.lower()
        ][:25]


async def setup(bot) -> None:
    await bot.add_cog(ScheduleCommands(bot))
