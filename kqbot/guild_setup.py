"""Creates (or finds) everything the bot needs in a server.

Safe to run repeatedly: anything that already exists is reused, so running it
again only fills in what's missing, such as a channel someone deleted.
"""

from dataclasses import dataclass, field

import discord

from kqbot.db import Database, GuildSettings
from kqbot.events import Event, normalize_emoji
from kqbot.formatting import roles_message
from kqbot.role_safety import unsafe_reason

ALERTS_CHANNEL = "kq-alerts"
ROLES_CHANNEL = "kq-roles"
REASON = "Fiesta KQ Bot setup"


@dataclass
class SetupReport:
    created: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.created:
            return "Everything was already set up. Nothing to change."
        return "Created: " + ", ".join(self.created)


def _read_only_overwrites(guild: discord.Guild) -> dict:
    """Members can read and react with existing emojis, but not post or add new ones."""
    return {
        guild.default_role: discord.PermissionOverwrite(send_messages=False, add_reactions=False),
        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            add_reactions=True,
            read_message_history=True,
        ),
    }


async def _ensure_role(
    guild: discord.Guild, event: Event, stored_id: int | None, report: SetupReport
) -> discord.Role:
    role = guild.get_role(stored_id) if stored_id else None
    if role is not None and (reason := unsafe_reason(role)):
        # Someone gave the event role real permissions. Stop handing it out.
        report.created.append(f"stopped using @{role.name} for {event.name} because {reason}")
        role = None
    elif role is not None:
        if role.name != event.name:
            # The event was renamed; keep the role (and who has it), update its name.
            old_name = role.name
            await role.edit(name=event.name, reason=REASON)
            report.created.append(f"renamed @{old_name} to @{event.name}")
        else:
            report.reused.append(f"role {event.name}")
        return role

    # Reuse a same-named role only if it's a harmless ping role; never e.g. a
    # "Moderator" role that happens to share an event's name.
    existing = discord.utils.get(guild.roles, name=event.name)
    if existing is not None and not unsafe_reason(existing):
        report.reused.append(f"role {event.name}")
        return existing
    # No permissions; mentionable so reminder pings actually notify people.
    role = await guild.create_role(
        name=event.name,
        permissions=discord.Permissions.none(),
        mentionable=True,
        reason=REASON,
    )
    report.created.append(f"role @{event.name}")
    return role


async def _ensure_channel(
    guild: discord.Guild, stored_id: int | None, name: str, topic: str, report: SetupReport
) -> discord.TextChannel:
    channel = discord.utils.get(guild.text_channels, id=stored_id) if stored_id else None
    if channel is None:
        channel = discord.utils.get(guild.text_channels, name=name)
    if channel is not None:
        report.reused.append(f"channel #{channel.name}")
        return channel
    channel = await guild.create_text_channel(
        name, topic=topic, overwrites=_read_only_overwrites(guild), reason=REASON
    )
    report.created.append(f"channel #{name}")
    return channel


def _reaction_order_after_sync(message: discord.Message, wanted: list[str]) -> list[str]:
    """Order the bot's reactions would end up in if we only removed and added.

    Discord shows reactions in the order they were first added and can't
    reorder them, so new ones always land at the end.
    """
    kept = [
        emoji
        for emoji in (normalize_emoji(str(r.emoji)) for r in message.reactions if r.me)
        if emoji in wanted
    ]
    return kept + [emoji for emoji in wanted if emoji not in kept]


async def _ensure_roles_message(
    channel: discord.TextChannel,
    stored_id: int | None,
    events: tuple[Event, ...],
    role_ids: dict[str, int],
    report: SetupReport,
) -> discord.Message:
    content = roles_message(events, role_ids)
    # Show role mentions without pinging everyone who has them.
    no_pings = discord.AllowedMentions.none()
    wanted = [normalize_emoji(e.emoji) for e in events]

    message = None
    if stored_id:
        try:
            message = await channel.fetch_message(stored_id)
        except discord.NotFound:
            message = None

    if message is not None and _reaction_order_after_sync(message, wanted) != wanted:
        # The event order changed. Repost so the emojis match the list.
        # People keep their roles; only the reactions on the old message go.
        try:
            await message.delete()
        except discord.NotFound:
            pass
        message = await channel.send(content, allowed_mentions=no_pings)
        report.created.append(f"reposted role picker in #{channel.name} (new order)")
    elif message is None:
        message = await channel.send(content, allowed_mentions=no_pings)
        report.created.append(f"role picker message in #{channel.name}")
    elif message.content != content:
        await message.edit(content=content, allowed_mentions=no_pings)

    present = set()
    for reaction in message.reactions:
        if not reaction.me:
            continue
        emoji = normalize_emoji(str(reaction.emoji))
        if emoji in wanted:
            present.add(emoji)
        else:
            # Event removed.
            await message.remove_reaction(reaction.emoji, channel.guild.me)
    for event in events:
        if normalize_emoji(event.emoji) not in present:
            # from_str handles both Unicode and <:name:id> custom emojis.
            await message.add_reaction(discord.PartialEmoji.from_str(event.emoji))
    return message


async def ensure_guild_setup(
    guild: discord.Guild, events: tuple[Event, ...], db: Database
) -> SetupReport:
    report = SetupReport()
    settings = db.get_guild(guild.id) or GuildSettings(guild.id)

    stored_roles = db.get_event_roles(guild.id)
    role_ids: dict[str, int] = {}
    for event in events:
        role = await _ensure_role(guild, event, stored_roles.get(event.key), report)
        db.set_event_role(guild.id, event.key, role.id)
        role_ids[event.key] = role.id

    alerts = await _ensure_channel(
        guild, settings.alerts_channel_id, ALERTS_CHANNEL, "Kingdom Quest reminders", report
    )
    roles_channel = await _ensure_channel(
        guild,
        settings.roles_channel_id,
        ROLES_CHANNEL,
        "React to get pinged for Kingdom Quests",
        report,
    )
    settings.alerts_channel_id = alerts.id
    settings.roles_channel_id = roles_channel.id
    db.save_guild(settings)  # keep progress even if the message step fails

    message = await _ensure_roles_message(
        roles_channel, settings.roles_message_id, events, role_ids, report
    )
    settings.roles_message_id = message.id
    db.save_guild(settings)
    return report
