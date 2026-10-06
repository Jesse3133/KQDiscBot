"""Entry point: ``python -m kqbot``."""

import logging

import discord

from kqbot.bot import KQBot
from kqbot.config import load_config


def main() -> None:
    config = load_config()
    discord.utils.setup_logging(level=logging.INFO)
    KQBot(config).run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
