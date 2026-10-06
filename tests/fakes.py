"""Minimal stand-ins for discord.py objects, enough to exercise setup logic."""

from dataclasses import dataclass, field
from itertools import count
from unittest.mock import MagicMock

import discord

_ids = count(1000)


@dataclass(eq=False)  # hashable by identity, like discord.Role
class FakeRole:
    name: str
    mentionable: bool = False
    id: int = field(default_factory=lambda: next(_ids))


@dataclass
class FakeReaction:
    emoji: str
    me: bool = True


@dataclass
class FakeMessage:
    content: str
    id: int = field(default_factory=lambda: next(_ids))
    reactions: list = field(default_factory=list)
    edits: int = 0

    async def edit(self, content, allowed_mentions=None):
        self.content = content
        self.edits += 1

    async def add_reaction(self, emoji):
        self.reactions.append(FakeReaction(emoji))


@dataclass
class FakeChannel:
    name: str
    overwrites: dict = field(default_factory=dict)
    id: int = field(default_factory=lambda: next(_ids))
    messages: dict = field(default_factory=dict)

    async def send(self, content, allowed_mentions=None):
        message = FakeMessage(content)
        self.messages[message.id] = message
        return message

    async def fetch_message(self, message_id):
        if message_id not in self.messages:
            raise discord.NotFound(MagicMock(status=404, reason="Not Found"), "Unknown Message")
        return self.messages[message_id]


@dataclass
class FakeGuild:
    name: str = "Test Guild"
    id: int = field(default_factory=lambda: next(_ids))
    roles: list = field(default_factory=list)
    text_channels: list = field(default_factory=list)
    default_role: FakeRole = field(default_factory=lambda: FakeRole("@everyone"))
    me: FakeRole = field(default_factory=lambda: FakeRole("Fiesta KQ Bot"))

    def get_role(self, role_id):
        return next((r for r in self.roles if r.id == role_id), None)

    async def create_role(self, name, mentionable, reason):
        role = FakeRole(name, mentionable)
        self.roles.append(role)
        return role

    async def create_text_channel(self, name, topic, overwrites, reason):
        channel = FakeChannel(name, overwrites)
        self.text_channels.append(channel)
        return channel
