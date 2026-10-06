from discord import app_commands

from kqbot.events import Event


def event_choices(events: tuple[Event, ...], current: str) -> list[app_commands.Choice[str]]:
    """Autocomplete options for an ``event`` command parameter."""
    current = current.lower()
    return [
        app_commands.Choice(name=e.name, value=e.key) for e in events if current in e.name.lower()
    ][:25]
