"""Which roles the bot is willing to hand out through the role picker.

Event roles exist only to be pinged. The bot must never give out a role that
grants real power, even if one happens to share an event's name or someone
later adds permissions to an event role.
"""

import discord

# Permissions that make a role more than a ping tag.
POWERFUL = discord.Permissions(
    administrator=True,
    manage_guild=True,
    manage_roles=True,
    manage_channels=True,
    manage_messages=True,
    manage_webhooks=True,
    manage_nicknames=True,
    manage_expressions=True,
    manage_threads=True,
    manage_events=True,
    kick_members=True,
    ban_members=True,
    moderate_members=True,
    mention_everyone=True,
    view_audit_log=True,
    move_members=True,
    mute_members=True,
    deafen_members=True,
)


def unsafe_reason(role: discord.Role) -> str | None:
    """Why the bot must not hand this role out, or None if it's fine."""
    if role.is_default():
        return "it's @everyone"
    if role.managed:
        return "it belongs to a bot or integration"
    powerful = [name for name, on in role.permissions if on and getattr(POWERFUL, name)]
    if powerful:
        return "it has powerful permissions (" + ", ".join(sorted(powerful)) + ")"
    return None
