from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from kqbot.cogs.common import event_choices
from kqbot.formatting import next_line


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
        schedule = self.bot.schedule
        rows = sorted(
            ((schedule.next(e, now), schedule.current(e, now)) for e in events),
            # Open recruitment first, then soonest start.
            key=lambda pair: (pair[1] is None, pair[0].start),
        )
        lines = [next_line(upcoming, active) for upcoming, active in rows]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @next_cmd.autocomplete("event")
    async def event_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return event_choices(self.bot.events, current)


async def setup(bot) -> None:
    await bot.add_cog(ScheduleCommands(bot))
