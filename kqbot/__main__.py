"""Entry point: ``python -m kqbot``."""

import logging
import signal

import discord

from kqbot.bot import KQBot
from kqbot.config import load_config


def _stop(signum, frame) -> None:
    raise KeyboardInterrupt


def main() -> None:
    config = load_config()
    discord.utils.setup_logging(level=logging.INFO)
    # Hosts and Docker stop the bot with SIGTERM. Treat it like Ctrl+C so the
    # bot logs out and closes the database cleanly.
    signal.signal(signal.SIGTERM, _stop)
    KQBot(config).run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
